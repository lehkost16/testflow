from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.module import Module
from app.models.testcase import TestCase, ExecutionStatus, TestCaseStatus
from app.models.test_case_archive import ProjectArchive, ArchivedTestCase, ArchiveStatus
from app.api.project_test_cases import check_project_access, check_project_edit_permission, export_to_xmind, export_to_csv
from app.core.dependencies import get_current_active_user

router = APIRouter()

# --- Schemas ---

class ArchiveCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    test_case_ids: Optional[List[int]] = None  # If None/Empty, archive all cases in project? Or require explicit selection?
    # User requirement: "choose create archive, can select current project specified cases to archive"

class ArchiveResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    created_by_name: str
    case_count: int

    class Config:
        from_attributes = True

class ArchivedTestCaseResponse(BaseModel):
    id: int
    original_case_id: Optional[int]
    title: str
    description: Optional[str] = None
    preconditions: Optional[str] = None
    test_steps: Optional[List[dict]] = None
    expected_result: Optional[str] = None
    module_name: Optional[str] = None
    module_full_path: Optional[str] = None
    priority: Optional[str] = None
    test_category: Optional[str] = None
    design_method: Optional[str] = None
    execution_status: str
    execution_comment: Optional[str] = None
    step_execution_results: Optional[Dict[str, Any]] = None
    updated_at: datetime
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True

class ExecutionUpdateStep(BaseModel):
    status: str # passed, failed, etc.
    actual: Optional[str] = None

class ExecutionUpdateRequest(BaseModel):
    status: ExecutionStatus
    comment: Optional[str] = None
    step_results: Optional[Dict[str, ExecutionUpdateStep]] = None # key is step index (str)

class ExportArchiveRequest(BaseModel):
    format: str = "xmind" # xmind, excel

# --- Helpers ---

def get_module_full_path(module: Module, all_modules_dict: Dict[int, Module]) -> str:
    # Module model is currently flat (no parent_id), so full path is just the name.
    return module.name

# --- Endpoints ---

@router.post("/projects/{project_id}/archives", response_model=ArchiveResponse)
async def create_archive(
    project_id: int,
    request: ArchiveCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建测试用例归档"""
    check_project_edit_permission(project_id, current_user, db)

    # 1. Validate Project & Input
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not request.test_case_ids:
        raise HTTPException(status_code=400, detail="请选择要归档的测试用例")

    # 2. Fetch Test Cases
    # Only fetch active cases
    
    # Logic to find all cases belonging to project (direct or indirect)
    from sqlalchemy import or_
    from app.models.requirement import RequirementPoint
    from app.models.testcase import TestPoint

    # 1. Direct project cases
    # 2. Module cases (modules belong to project)
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_ids = [m.id for m in modules]

    # 3. Test Point cases (test points -> requirements -> modules -> project)
    rp_ids = []
    if module_ids:
        rp_ids = [rp.id for rp in db.query(RequirementPoint.id).filter(
            RequirementPoint.module_id.in_(module_ids)
        ).all()]
    
    tp_ids = []
    if rp_ids:
        tp_ids = [tp.id for tp in db.query(TestPoint.id).filter(
            TestPoint.requirement_point_id.in_(rp_ids)
        ).all()]

    filters = [TestCase.project_id == project_id]
    if module_ids:
        filters.append(TestCase.module_id.in_(module_ids))
    if tp_ids:
        filters.append(TestCase.test_point_id.in_(tp_ids))

    test_cases = db.query(TestCase).filter(
        TestCase.id.in_(request.test_case_ids),
        or_(*filters)
    ).all()
    
    if len(test_cases) != len(request.test_case_ids):
        # Some IDs might be invalid or belong to other projects
        pass # We'll just archive what we found
    
    if not test_cases:
        raise HTTPException(status_code=400, detail="未找到有效的测试用例")

    # 3. Create Archive Record
    archive = ProjectArchive(
        project_id=project_id,
        name=request.name,
        description=request.description,
        created_by=current_user.id,
        status=ArchiveStatus.ACTIVE
    )
    db.add(archive)
    db.flush() # Get ID

    # 4. Snapshot Modules for Path Resolution
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_map = {m.id: m for m in modules}

    # 5. Create Archived Cases
    archived_cases = []
    for tc in test_cases:
        # Resolve Module Path
        module_name = "未分类"
        module_full_path = "未分类"
        if tc.module_id and tc.module_id in module_map:
            mod = module_map[tc.module_id]
            module_name = mod.name
            module_full_path = get_module_full_path(mod, module_map)
        elif tc.import_module_name:
             module_name = tc.import_module_name
             module_full_path = tc.import_module_name

        ac = ArchivedTestCase(
            archive_id=archive.id,
            original_case_id=tc.id,
            title=tc.title,
            description=tc.description,
            preconditions=tc.preconditions,
            test_steps=tc.test_steps,
            expected_result=tc.expected_result,
            module_name=module_name,
            module_full_path=module_full_path,
            priority=tc.priority,
            test_category=tc.test_category,
            design_method=tc.design_method,
            execution_status=ExecutionStatus.SKIPPED # Default
        )
        archived_cases.append(ac)
    
    db.add_all(archived_cases)
    db.commit()
    db.refresh(archive)
    
    return ArchiveResponse(
        id=archive.id,
        name=archive.name,
        description=archive.description,
        status=archive.status,
        created_at=archive.created_at,
        created_by_name=current_user.username, # Assuming user has username
        case_count=len(archived_cases)
    )

@router.get("/projects/{project_id}/archives", response_model=List[ArchiveResponse])
async def list_archives(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取项目下的归档列表"""
    check_project_access(project_id, current_user, db)
    
    archives = db.query(ProjectArchive).filter(
        ProjectArchive.project_id == project_id
    ).order_by(ProjectArchive.created_at.desc()).all()
    
    result = []
    for a in archives:
        # Count cases (could be optimized with group_by query, but list shouldn't be too long)
        count = db.query(ArchivedTestCase).filter(
            ArchivedTestCase.archive_id == a.id
        ).count()
        
        result.append(ArchiveResponse(
            id=a.id,
            name=a.name,
            description=a.description,
            status=a.status,
            created_at=a.created_at,
            created_by_name=a.creator.username if a.creator else "Unknown",
            case_count=count
        ))
    return result

@router.get("/archives/{archive_id}/test-cases", response_model=List[ArchivedTestCaseResponse])
async def list_archive_cases(
    archive_id: int,
    module_path: Optional[str] = None, # Filter by module path?
    status: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取归档下的测试用例"""
    archive = db.query(ProjectArchive).filter(ProjectArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
        
    check_project_access(archive.project_id, current_user, db)

    query = db.query(ArchivedTestCase).filter(ArchivedTestCase.archive_id == archive_id)
    
    if status:
        query = query.filter(ArchivedTestCase.execution_status == status)
        
    cases = query.all()
    
    return [
        ArchivedTestCaseResponse(
            id=c.id,
            original_case_id=c.original_case_id,
            title=c.title,
            description=c.description,
            preconditions=c.preconditions,
            test_steps=c.test_steps,
            expected_result=c.expected_result,
            module_name=c.module_name,
            module_full_path=c.module_full_path,
            priority=c.priority,
            test_category=c.test_category,
            design_method=c.design_method,
            execution_status=c.execution_status,
            execution_comment=c.execution_comment,
            step_execution_results=c.step_execution_results,
            updated_at=c.updated_at,
            updated_by_name=c.updater.username if c.updater else None
        )
        for c in cases
    ]

@router.put("/archives/cases/{case_id}/execution", response_model=ArchivedTestCaseResponse)
async def update_execution_result(
    case_id: int,
    request: ExecutionUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新归档用例执行结果"""
    case = db.query(ArchivedTestCase).filter(ArchivedTestCase.id == case_id).first()
    if not case:
         raise HTTPException(status_code=404, detail="Case not found")
    
    # Check perm via archive->project
    archive = db.query(ProjectArchive).filter(ProjectArchive.id == case.archive_id).first()
    check_project_edit_permission(archive.project_id, current_user, db)
    
    # Update
    case.execution_status = request.status
    if request.comment is not None:
        case.execution_comment = request.comment
    if request.step_results is not None:
        # Convert Pydantic models to dict for JSON storage
        case.step_execution_results = {k: v.dict() for k, v in request.step_results.items()}
        
    case.updated_by = current_user.id
    db.commit()
    db.refresh(case)
    
    return ArchivedTestCaseResponse(
            id=case.id,
            original_case_id=case.original_case_id,
            title=case.title,
            description=case.description,
            preconditions=case.preconditions,
            test_steps=case.test_steps,
            expected_result=case.expected_result,
            module_name=case.module_name,
            module_full_path=case.module_full_path,
            priority=case.priority,
            test_category=case.test_category,
            design_method=case.design_method,
            execution_status=case.execution_status,
            execution_comment=case.execution_comment,
            step_execution_results=case.step_execution_results,
            updated_at=case.updated_at,
            updated_by_name=case.updater.username if case.updater else None
    )

@router.post("/archives/{archive_id}/export")
async def export_archive(
    archive_id: int,
    request: ExportArchiveRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """导出归档用例和结果"""
    archive = db.query(ProjectArchive).filter(ProjectArchive.id == archive_id).first()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
        
    check_project_access(archive.project_id, current_user, db)
    
    cases = db.query(ArchivedTestCase).filter(ArchivedTestCase.archive_id == archive_id).all()
    
    # Need to adapt ArchivedTestCase to what export functions expect
    # or create new export functions.
    # The existing export functions expect TestCase objects with relations (test_point, module, etc.)
    # ArchivedTestCase has flattened module info.
    # It's safer to duplicated the export logic here for Archives, tailored to the flatten structure.
    
    if request.format == "xmind":
        return export_archive_to_xmind(archive, cases)
    elif request.format == "markdown":
        return export_archive_to_markdown(archive, cases)
    else:
        return export_archive_to_csv(archive, cases)

def export_archive_to_markdown(archive: ProjectArchive, cases: List[ArchivedTestCase]):
    from fastapi.responses import StreamingResponse
    from io import StringIO
    from urllib.parse import quote
    
    output = StringIO()
    
    priority_map = {"high": "高", "medium": "中", "low": "低"}
    status_map = {
        "passed": "通过", "failed": "失败", "blocked": "阻塞", 
        "skipped": "跳过", "in_progress": "进行中"
    }
    
    # 1. Statistics
    total = len(cases)
    passed = sum(1 for c in cases if c.execution_status == ExecutionStatus.PASSED)
    failed = sum(1 for c in cases if c.execution_status == ExecutionStatus.FAILED)
    blocked = sum(1 for c in cases if c.execution_status == ExecutionStatus.BLOCKED)
    skipped = sum(1 for c in cases if c.execution_status == ExecutionStatus.SKIPPED)
    
    output.write(f"# {archive.name} - 执行测试报告\n\n")
    output.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    output.write("## 执行概览\n\n")
    output.write(f"- **总计用例**: {total}\n")
    output.write(f"- **通过 (Passed)**: {passed}\n")
    output.write(f"- **失败 (Failed)**: {failed}\n")
    output.write(f"- **阻塞 (Blocked)**: {blocked}\n")
    output.write(f"- **跳过 (Skipped)**: {skipped}\n")
    pass_rate = (passed / total * 100) if total > 0 else 0.0
    output.write(f"- **通过率**: {pass_rate:.2f}%\n\n")
    
    # 2. Failed/Blocked Details
    abnormal_cases = [c for c in cases if c.execution_status in (ExecutionStatus.FAILED, ExecutionStatus.BLOCKED)]
    if abnormal_cases:
        output.write("## 异常用例详情\n\n")
        for i, c in enumerate(abnormal_cases, 1):
            status_val = c.execution_status.value if hasattr(c.execution_status, 'value') else str(c.execution_status)
            status_emoji = "❌" if status_val == "failed" else "🚫"
            status_text = status_map.get(status_val, status_val)
            
            output.write(f"### {i}. {status_emoji} {c.title}\n")
            output.write(f"- **ID**: {c.id}\n")
            output.write(f"- **模块**: {c.module_full_path}\n")
            output.write(f"- **状态**: {status_text}\n")
            if c.execution_comment:
                output.write(f"- **备注**: {c.execution_comment}\n")
            
            # Step Failures
            if c.step_execution_results:
                failed_steps = [
                   (k, v) for k, v in c.step_execution_results.items() 
                   if v.get('status') in ('failed', 'blocked')
                ]
                if failed_steps:
                    output.write("- **失败步骤**:\n")
                    for k, v in failed_steps:
                        output.write(f"  - 步骤 {k}: {v.get('status')} - 实际结果: {v.get('actual')}\n")
            output.write("\n")
            
    # 3. All Cases List
    output.write("## 所有用例列表\n\n")
    output.write("| ID | 模块 | 标题 | 优先级 | 状态 | 备注 |\n")
    output.write("|----|------|------|--------|------|------|\n")

    for c in cases:
        prio = priority_map.get(c.priority, c.priority or "")
        # Handle enum or string properly
        status_val = c.execution_status.value if hasattr(c.execution_status, 'value') else str(c.execution_status)
        stat = status_map.get(status_val, status_val)
        
        comment = (c.execution_comment or "").replace("\n", " ")
        output.write(f"| {c.id} | {c.module_full_path} | {c.title} | {prio} | {stat} | {comment} |\n")

    output.seek(0)
    filename = f"{archive.name}_测试报告_{datetime.now().strftime('%Y%m%d')}.md"
    encoded_filename = quote(filename)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )
    from fastapi.responses import StreamingResponse
    from io import StringIO
    from urllib.parse import quote
    import csv

    output = StringIO()
    writer = csv.writer(output)

    headers = [
        "序号", "所属模块", "用例名称", "前置条件",
        "步骤", "预期", "优先级", "用例类型", "适用阶段", 
        "执行状态", "执行备注" # Added execution columns
    ]
    # Maybe add "Step Results"? it's complex in CSV.
    writer.writerow(headers)
    
    priority_map = {"high": "高", "medium": "中", "low": "低"}
    status_map = {
        "passed": "通过", "failed": "失败", "blocked": "阻塞", 
        "skipped": "跳过", "in_progress": "进行中"
    }
    
    for idx, tc in enumerate(cases, 1):
        steps_text = ""
        expected_text = ""
        if tc.test_steps and isinstance(tc.test_steps, list):
            steps_lines = []
            expected_lines = []
            for i, step in enumerate(tc.test_steps, 1):
                # Include step execution result?
                # Format: 1. Action [Passed]
                
                action = step.get("action", "") if isinstance(step, dict) else str(step)
                expected = step.get("expected", "") if isinstance(step, dict) else ""
                
                step_status_str = ""
                if tc.step_execution_results:
                    # check if index is str key "1" or integer
                    s_res = tc.step_execution_results.get(str(i))
                    if s_res:
                         s_status = status_map.get(s_res.get("status"), s_res.get("status"))
                         step_status_str = f" [{s_status}]"
                         if s_res.get("actual"):
                             step_status_str += f" 实际: {s_res.get('actual')}"
                
                steps_lines.append(f"{i}. {action}{step_status_str}")
                expected_lines.append(f"{i}. {expected}")
            steps_text = "\n".join(steps_lines)
            expected_text = "\n".join(expected_lines)

        writer.writerow([
            idx,
            tc.module_full_path or "未分类",
            tc.title,
            tc.preconditions or "",
            steps_text,
            expected_text,
            priority_map.get(tc.priority, tc.priority),
            tc.test_category or "",
            tc.design_method or "",
            status_map.get(tc.execution_status, tc.execution_status),
            tc.execution_comment or ""
        ])
    
    output.seek(0)
    filename = f"{archive.name}_归档用例_{datetime.now().strftime('%Y%m%d')}.csv"
    encoded_filename = quote(filename)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )

def export_archive_to_xmind(archive: ProjectArchive, cases: List[ArchivedTestCase]):
    from app.lib.xmind2testcase.writer import write_xmind_zip
    from app.lib.xmind2testcase.metadata import TestSuite as XMindTestSuite, TestCase as XMindTestCase, TestStep as XMindTestStep
    from fastapi.responses import StreamingResponse
    from urllib.parse import quote
    import re

    root_suite = XMindTestSuite(name=f"{archive.name}")
    root_suite.sub_suites = []
    suite_cache = {}

    def get_or_create_suite(path_names):
        if not path_names: return root_suite
        current_path = []
        parent = root_suite
        for name in path_names:
            current_path.append(name)
            path_key = tuple(current_path)
            if path_key not in suite_cache:
                new_suite = XMindTestSuite(name=name)
                if not parent.sub_suites: parent.sub_suites = []
                parent.sub_suites.append(new_suite)
                suite_cache[path_key] = new_suite
            parent = suite_cache[path_key]
        return parent

    for tc in cases:
        # User module_full_path
        if tc.module_full_path:
             full_path = tc.module_full_path.split("/")
        else:
             full_path = ["未分类"]
             
        # Title split logic (same as normal export)
        title_parts = [p.strip() for p in re.split(r'[-/\\—]+', tc.title) if p.strip()]
        if len(title_parts) > 1:
            title_path = title_parts[:-1]
            case_name = title_parts[-1]
            # Merge if overlaps
            if full_path and full_path != ["未分类"] and title_path and title_path[0] == full_path[0]:
                i = 0
                while i < len(full_path) and i < len(title_path) and full_path[i] == title_path[i]:
                    i += 1
                full_path.extend(title_path[i:])
            elif full_path == ["未分类"]:
                full_path = title_path
            else:
                full_path.extend(title_path)
        else:
            case_name = tc.title

        target_suite = get_or_create_suite(full_path)
        
        steps = []
        if tc.test_steps and isinstance(tc.test_steps, list):
            for idx, step_data in enumerate(tc.test_steps, 1):
                if isinstance(step_data, dict):
                    # Append result to action/expected?
                    # XMind doesn't standardly support execution results, but we can append to text.
                    action = step_data.get("action", "")
                    
                    s_res = ""
                    if tc.step_execution_results and str(idx) in tc.step_execution_results:
                         res_data = tc.step_execution_results[str(idx)]
                         if res_data.get("status") == "failed":
                             s_res = f" [FAIL: {res_data.get('actual','')}]"
                         elif res_data.get("status") == "passed":
                             s_res = " [PASS]"
                    
                    steps.append(XMindTestStep(
                        step_number=idx,
                        actions=action + s_res,
                        expectedresults=step_data.get("expected", "")
                    ))

        # Add result to summary/note
        summary = tc.description or ""
        summary += f"\n\n[归档执行结果] {tc.execution_status}"
        if tc.execution_comment:
            summary += f"\n备注: {tc.execution_comment}"

        case = XMindTestCase(
            name=case_name,
            summary=summary,
            preconditions=tc.preconditions or "",
            importance=2, # Map priority?
            execution_type=1,
            steps=steps,
            tc_id=str(tc.id) # Use archived ID
        )
        
        if not target_suite.testcase_list:
            target_suite.testcase_list = []
        target_suite.testcase_list.append(case)

    xmind_bytes = write_xmind_zip([root_suite])
    filename = f"{archive.name}_归档_{datetime.now().strftime('%Y%m%d')}.xmind"
    encoded_filename = quote(filename)

    return StreamingResponse(
        xmind_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )
