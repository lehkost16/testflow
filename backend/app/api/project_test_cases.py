"""
项目级测试用例管理API
提供项目下所有模块测试用例的聚合查询和批量操作
"""
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User, ProjectMember, ProjectRole
from app.models.project import Project
from app.models.module import Module
from app.lib.xmind2testcase.writer import write_xmind_zip
from app.lib.xmind2testcase.metadata import TestSuite as XMindTestSuite, TestCase as XMindTestCase, TestStep as XMindTestStep
from app.models.requirement import RequirementPoint
from app.models.testcase import TestPoint, TestCase, TestCaseStatus
from app.core.dependencies import get_current_active_user

router = APIRouter()


# ========== Pydantic 响应模型 ==========

class TestCaseItem(BaseModel):
    """测试用例扁平化展示"""
    id: int
    title: str
    description: Optional[str] = None
    preconditions: Optional[str] = None
    test_steps: Optional[List[dict]] = None
    expected_result: Optional[str] = None
    design_method: Optional[str] = None
    test_category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    module_id: Optional[int] = None
    module_name: Optional[str] = None
    test_point_id: Optional[int] = None
    test_point_content: Optional[str] = None

    class Config:
        from_attributes = True


class ModuleTestCasesGroup(BaseModel):
    """按模块分组的测试用例"""
    id: int
    name: str
    test_cases: List[TestCaseItem]

    class Config:
        from_attributes = True


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    ids: List[int]


# ========== 权限检查 ==========

def check_project_access(project_id: int, user: User, db: Session) -> Project:
    """检查用户对项目的访问权限，返回项目对象"""
    from app.models.user import UserRole

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 管理员或项目所有者
    if user.role == UserRole.ADMIN or project.owner_id == user.id:
        return project

    # 检查是否为项目成员
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="无权访问此项目")

    return project


def check_project_edit_permission(project_id: int, user: User, db: Session) -> Project:
    """检查用户是否有编辑权限（成员或管理员）"""
    from app.models.user import UserRole

    project = check_project_access(project_id, user, db)

    # 管理员或项目所有者
    if user.role == UserRole.ADMIN or project.owner_id == user.id:
        return project

    # 检查是否为编辑角色
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()

    if member and member.role == ProjectRole.VIEWER:
        raise HTTPException(status_code=403, detail="查看者无编辑权限")

    return project


# ========== API 路由 ==========

@router.get("/projects/{project_id}/test-cases", response_model=List[Any])
async def get_project_test_cases(
    project_id: int,
    view_mode: str = Query("hierarchy", regex="^(hierarchy|flat)$"),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取项目下所有模块的测试用例

    - view_mode: hierarchy (按模块分组) | flat (扁平列表)
    - keyword: 搜索标题/内容
    - status: 筛选状态
    - priority: 筛选优先级
    """
    # 权限检查
    check_project_access(project_id, current_user, db)

    # 获取项目下所有模块
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_ids = [m.id for m in modules]
    module_map = {m.id: m.name for m in modules}

    if not module_ids:
        return []

    # 获取所有模块的需求点
    requirement_points = db.query(RequirementPoint).filter(
        RequirementPoint.module_id.in_(module_ids)
    ).all()
    rp_ids = [rp.id for rp in requirement_points]
    rp_module_map = {rp.id: rp.module_id for rp in requirement_points}



    # 获取所有测试点
    test_points = db.query(TestPoint).filter(
        TestPoint.requirement_point_id.in_(rp_ids)
    ).all()
    tp_ids = [tp.id for tp in test_points]
    tp_rp_map = {tp.id: tp.requirement_point_id for tp in test_points}
    tp_content_map = {tp.id: tp.content for tp in test_points}



    # 构建测试用例查询
    # 构建测试用例查询
    query = db.query(TestCase).filter(
        or_(
            TestCase.test_point_id.in_(tp_ids),
            TestCase.module_id.in_(module_ids),
            TestCase.project_id == project_id
        )
    )

    # 应用筛选条件
    if keyword:
        query = query.filter(TestCase.title.ilike(f"%{keyword}%"))
    if status:
        query = query.filter(TestCase.status == status)
    if priority:
        query = query.filter(TestCase.priority == priority)

    test_cases = query.all()

    # 构建响应
    if view_mode == "flat":
        result = []
        for tc in test_cases:
            tp_id = tc.test_point_id
            rp_id = tp_rp_map.get(tp_id)
            module_id = rp_module_map.get(rp_id) if rp_id else None

            # 确定模块信息
            final_module_id = tc.module_id if tc.module_id else module_id
            final_module_name = "未分类"
            if final_module_id:
                final_module_name = module_map.get(final_module_id, "未分类")
            elif tc.import_module_name:
                final_module_name = tc.import_module_name

            result.append(TestCaseItem(
                id=tc.id,
                title=tc.title,
                description=tc.description,
                preconditions=tc.preconditions,
                test_steps=tc.test_steps,
                expected_result=tc.expected_result,
                design_method=tc.design_method,
                test_category=tc.test_category,
                priority=tc.priority,
                status=tc.status,
                module_id=final_module_id,
                module_name=final_module_name,
                test_point_id=tp_id,
                test_point_content=tp_content_map.get(tp_id)
            ).model_dump())
        return result

    # hierarchy 模式：按模块分组
    module_cases = {m.id: [] for m in modules}
    module_cases[0] = []  # 未分类

    for tc in test_cases:
        tp_id = tc.test_point_id
        rp_id = tp_rp_map.get(tp_id)

        # 确定模块归属
        # 1. 优先使用直接关联的 module_id
        # 2. 其次使用通过测试点关联的 module_id
        # 3. 如果都没有，则归为未分类 (0)
        module_id = tc.module_id if tc.module_id else (rp_module_map.get(rp_id) if rp_id else 0)

        # 确定模块名称显示
        module_name = "未分类"
        if module_id:
            module_name = module_map.get(module_id, "未分类")
        elif tc.import_module_name:
            # 如果是未分类但有导入时的模块名，显示该名称（但在分组时仍归为未分类）
            module_name = tc.import_module_name

        item = TestCaseItem(
            id=tc.id,
            title=tc.title,
            description=tc.description,
            preconditions=tc.preconditions,
            test_steps=tc.test_steps,
            expected_result=tc.expected_result,
            design_method=tc.design_method,
            test_category=tc.test_category,
            priority=tc.priority,
            status=tc.status,
            module_id=module_id,
            module_name=module_name,
            test_point_id=tp_id,
            test_point_content=tp_content_map.get(tp_id)
        )

        if module_id in module_cases:
            module_cases[module_id].append(item.model_dump())
        else:
            module_cases[0].append(item.model_dump())

    result = [
        ModuleTestCasesGroup(id=m.id, name=m.name, test_cases=module_cases.get(m.id, [])).model_dump()
        for m in modules
    ]

    # 添加未分类（如果有）
    if module_cases[0]:
        result.append(ModuleTestCasesGroup(id=0, name="未分类", test_cases=module_cases[0]).model_dump())

    return result


@router.delete("/projects/{project_id}/test-cases/batch")
async def batch_delete_test_cases(
    project_id: int,
    request: BatchDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """批量删除测试用例"""
    # 权限检查（需要编辑权限）
    check_project_edit_permission(project_id, current_user, db)

    if not request.ids:
        raise HTTPException(status_code=400, detail="请选择要删除的用例")

    # 验证用例属于该项目
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_ids = [m.id for m in modules]

    rp_ids = [rp.id for rp in db.query(RequirementPoint.id).filter(
        RequirementPoint.module_id.in_(module_ids)
    ).all()]

    tp_ids = [tp.id for tp in db.query(TestPoint.id).filter(
        TestPoint.requirement_point_id.in_(rp_ids)
    ).all()]

    # 执行删除
    # 只要满足以下任一条件即可删除：
    # 1. 属于该项目的测试点
    # 2. 属于该项目的模块
    # 3. 直接属于该项目（未分类/导入）
    filters = [TestCase.project_id == project_id]
    if module_ids:
        filters.append(TestCase.module_id.in_(module_ids))
    if tp_ids:
        filters.append(TestCase.test_point_id.in_(tp_ids))

    deleted = db.query(TestCase).filter(
        TestCase.id.in_(request.ids),
        or_(*filters)
    ).delete(synchronize_session=False)

    db.commit()

    return {"deleted_count": deleted, "message": f"成功删除 {deleted} 条用例"}


class TestCaseUpdateRequest(BaseModel):
    """测试用例更新请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    preconditions: Optional[str] = None
    test_steps: Optional[List[dict]] = None
    expected_result: Optional[str] = None
    design_method: Optional[str] = None
    test_category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    module_id: Optional[int] = None


def verify_test_case_belongs_to_project(case_id: int, project_id: int, db: Session) -> TestCase:
    """验证测试用例属于指定项目，返回用例对象"""
    # 获取项目的所有模块
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_ids = [m.id for m in modules]

    # 获取模块的需求点
    rp_ids = []
    if module_ids:
        rp_ids = [rp.id for rp in db.query(RequirementPoint.id).filter(
            RequirementPoint.module_id.in_(module_ids)
        ).all()]

    # 获取测试点
    tp_ids = []
    if rp_ids:
        tp_ids = [tp.id for tp in db.query(TestPoint.id).filter(
            TestPoint.requirement_point_id.in_(rp_ids)
        ).all()]

    # 查找测试用例（支持通过 test_point_id 或直接 module_id 或直接 project_id 验证）
    test_case = db.query(TestCase).filter(
        TestCase.id == case_id,
        or_(
            TestCase.test_point_id.in_(tp_ids) if tp_ids else False,
            TestCase.module_id.in_(module_ids) if module_ids else False,
            TestCase.project_id == project_id
        )
    ).first()

    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在或不属于此项目")

    return test_case


@router.put("/projects/{project_id}/test-cases/{case_id}")
async def update_test_case(
    project_id: int,
    case_id: int,
    request: TestCaseUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新单个测试用例"""
    # 权限检查
    check_project_edit_permission(project_id, current_user, db)

    # 验证用例属于该项目
    test_case = verify_test_case_belongs_to_project(case_id, project_id, db)

    # 更新字段
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(test_case, key, value)

    test_case.edited_by_user = True
    db.commit()
    db.refresh(test_case)

    return {"message": "更新成功", "id": test_case.id}


@router.delete("/projects/{project_id}/test-cases/{case_id}")
async def delete_single_test_case(
    project_id: int,
    case_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除单个测试用例"""
    # 权限检查
    check_project_edit_permission(project_id, current_user, db)

    # 验证用例属于该项目
    test_case = verify_test_case_belongs_to_project(case_id, project_id, db)

    # 执行删除
    db.delete(test_case)
    db.commit()

    return {"message": "删除成功", "id": case_id}


class ExportRequest(BaseModel):
    """导出请求"""
    ids: Optional[List[int]] = None  # 指定导出的用例ID，为空则导出全部
    format: str = "csv"  # 导出格式：excel, xmind


@router.post("/projects/{project_id}/test-cases/export")
async def export_test_cases(
    project_id: int,
    request: ExportRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    导出测试用例

    支持格式：
    - excel: Excel表格（测试步骤和预期结果分列展示）
    - xmind: 思维导图（按模块-用例-步骤层级展示）
    Excel列格式：
    - 序号
    - 所属模块
    - 用例标题
    - 前置条件
    - 测试步骤（多步骤以1. 2. 3.格式换行展示）
    - 预期结果（对应步骤以1. 2. 3.格式换行展示）
    - 优先级
    - 测试分类
    - 设计方法
    - 状态
    """
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from datetime import datetime
    from urllib.parse import quote

    # 权限检查
    check_project_access(project_id, current_user, db)

    # 获取项目信息
    project = db.query(Project).filter(Project.id == project_id).first()

    # 获取项目下所有模块
    modules = db.query(Module).filter(Module.project_id == project_id).all()
    module_ids = [m.id for m in modules]
    module_map = {m.id: m.name for m in modules}

    if not module_ids:
        raise HTTPException(status_code=400, detail="项目下没有模块")

    # 获取所有模块的需求点
    requirement_points = db.query(RequirementPoint).filter(
        RequirementPoint.module_id.in_(module_ids)
    ).all()
    rp_ids = [rp.id for rp in requirement_points]
    rp_module_map = {rp.id: rp.module_id for rp in requirement_points}



    # 获取所有测试点
    test_points = db.query(TestPoint).filter(
        TestPoint.requirement_point_id.in_(rp_ids)
    ).all()
    tp_ids = [tp.id for tp in test_points]
    tp_rp_map = {tp.id: tp.requirement_point_id for tp in test_points}



    # 构建测试用例查询
    query = db.query(TestCase).filter(
        or_(
            TestCase.test_point_id.in_(tp_ids),
            TestCase.module_id.in_(module_ids),
            TestCase.project_id == project_id
        )
    )

    # 如果指定了ID，只导出指定的用例
    if request.ids:
        query = query.filter(TestCase.id.in_(request.ids))

    test_cases = query.order_by(TestCase.id).all()

    if not test_cases:
        raise HTTPException(status_code=400, detail="没有可导出的测试用例")

    # 根据格式生成不同的文件
    if request.format == "xmind":
        return export_to_xmind(project, modules, test_cases, tp_rp_map, rp_module_map)
    else:
        return export_to_csv(project, modules, test_cases, tp_rp_map, rp_module_map, module_map, db)


def export_to_csv(project, modules, test_cases, tp_rp_map, rp_module_map, module_map, db: Session):
    """导出到 CSV"""
    from fastapi.responses import StreamingResponse
    from io import StringIO
    from datetime import datetime
    from urllib.parse import quote
    import csv

    # CSV 内存流（注意：csv 用文本流）
    output = StringIO()
    writer = csv.writer(output)

    # 表头
    headers = [
        "序号", "所属模块", "用例名称", "前置条件",
        "步骤", "预期", "优先级", "用例类型", "适用阶段", "状态"
    ]
    writer.writerow(headers)

    # 映射关系
    priority_map = {"high": "高", "medium": "中", "low": "低"}
    status_map = {"draft": "草稿", "under_review": "评审中", "approved": "已通过"}

    # 测试分类
    from app.models.settings import TestCategory
    categories = db.query(TestCategory).filter(TestCategory.is_active == True).all()
    category_map = {c.code: c.name for c in categories}

    # 设计方法
    from app.models.settings import TestDesignMethod
    methods = db.query(TestDesignMethod).filter(TestDesignMethod.is_active == True).all()
    method_map = {m.code: m.name for m in methods}

    # 写数据
    for idx, tc in enumerate(test_cases, 1):

        # 模块名称解析逻辑（保持不变）
        tp_id = tc.test_point_id
        rp_id = tp_rp_map.get(tp_id) if tp_id else None
        module_id = rp_module_map.get(rp_id) if rp_id else tc.module_id

        module_name = "未分类"
        if module_id:
            module_name = module_map.get(module_id, "未分类")
        elif tc.import_module_name:
            module_name = tc.import_module_name

        # 步骤 / 预期（CSV 用 \n 没问题，Excel/WPS 能识别）
        steps_text = ""
        expected_text = ""
        if tc.test_steps and isinstance(tc.test_steps, list):
            steps_lines = []
            expected_lines = []
            for i, step in enumerate(tc.test_steps, 1):
                action = step.get("action", "") if isinstance(step, dict) else str(step)
                expected = step.get("expected", "") if isinstance(step, dict) else ""
                steps_lines.append(f"{i}. {action}")
                expected_lines.append(f"{i}. {expected}")
            steps_text = "\n".join(steps_lines)
            expected_text = "\n".join(expected_lines)

        writer.writerow([
            idx,                                                    # 序号
            module_name,                                            # 所属模块
            tc.title or "",                                         # 用例名称
            tc.preconditions or "",                                 # 前置条件
            steps_text,                                             # 步骤
            expected_text,                                          # 预期
            priority_map.get(tc.priority, tc.priority or ""),       # 优先级
            category_map.get(tc.test_category, tc.test_category or ""),  # 用例类型
            method_map.get(tc.design_method, tc.design_method or ""),    # 适用阶段
            status_map.get(tc.status, tc.status or "")              # 状态
        ])

    output.seek(0)

    # 文件名
    filename = f"{project.name}_测试用例_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    encoded_filename = quote(filename)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )



def export_to_xmind(project, modules, test_cases, tp_rp_map, rp_module_map):
    """
    导出到 XMind (Zen / 2020+ JSON 格式)，支持分级模块合并及标题层级切割
    """
    from fastapi.responses import StreamingResponse
    from datetime import datetime
    from urllib.parse import quote
    import re

    # 1️⃣ 初始化根套件
    root_suite = XMindTestSuite(name=f"{project.name} - 测试用例")
    root_suite.sub_suites = []

    # 2️⃣ 模块层级管理器
    # path_key (tuple of names) -> XMindTestSuite
    suite_cache = {}

    def get_or_create_suite(path_names):
        """递归获取或创建嵌套套件"""
        if not path_names:
            return root_suite
        
        current_path = []
        parent = root_suite
        
        for name in path_names:
            current_path.append(name)
            path_key = tuple(current_path)
            
            if path_key not in suite_cache:
                new_suite = XMindTestSuite(name=name)
                if not parent.sub_suites:
                    parent.sub_suites = []
                parent.sub_suites.append(new_suite)
                suite_cache[path_key] = new_suite
            
            parent = suite_cache[path_key]
        
        return parent

    # 3️⃣ 预处理系统模块
    module_id_to_base_path = {}
    for mod in modules:
        # 系统模块名可能包含 /
        base_path = [p.strip() for p in mod.name.replace("\\", "/").split("/") if p.strip()]
        # 确保基础路径的 Suite 存在
        get_or_create_suite(base_path)
        module_id_to_base_path[mod.id] = base_path

    # 4️⃣ 分类测试用例
    for tc in test_cases:
        # 确定归属模块路径
        tp_id = tc.test_point_id
        rp_id = tp_rp_map.get(tp_id) if tp_id else None
        module_id = rp_module_map.get(rp_id) if rp_id else tc.module_id

        # 初始路径
        if module_id and module_id in module_id_to_base_path:
            full_path = list(module_id_to_base_path[module_id])
        elif tc.import_module_name:
            full_path = [p.strip() for p in tc.import_module_name.replace("\\", "/").split("/") if p.strip()]
        else:
            full_path = ["未分类"]

        # 标题层级切割: "操作按钮 - 审核功能 - 图片收藏" -> ["操作按钮", "审核功能", "图片收藏"]
        # 支持多种常见分隔符如 - , / , \
        title_parts = [p.strip() for p in re.split(r'[-/\\—]+', tc.title) if p.strip()]
        
        if len(title_parts) > 1:
            # 前面部分作为路径
            title_path = title_parts[:-1]
            case_name = title_parts[-1]
            
            # 如果标题路径的第一部分已经在当前路径中，进行智能合并
            if full_path and full_path != ["未分类"] and title_path and title_path[0] == full_path[0]:
                i = 0
                while i < len(full_path) and i < len(title_path) and full_path[i] == title_path[i]:
                    i += 1
                # 拼接剩余不重叠的标题路径
                full_path.extend(title_path[i:])
            elif full_path == ["未分类"]:
                # 如果是未分类但标题有层级，直接以标题层级为准
                full_path = title_path
            else:
                # 否则追加层级
                full_path.extend(title_path)
        else:
            case_name = tc.title or "未命名用例"

        # 获取最终归属套件
        target_suite = get_or_create_suite(full_path)

        # 5️⃣ 组装 TestStep
        steps = []
        if tc.test_steps and isinstance(tc.test_steps, list):
            for idx, step_data in enumerate(tc.test_steps, 1):
                if isinstance(step_data, dict):
                    steps.append(
                        XMindTestStep(
                            step_number=idx,
                            actions=step_data.get("action") or step_data.get("actions") or "",
                            expectedresults=step_data.get("expected") or step_data.get("expectedresults") or ""
                        )
                    )

        # 6️⃣ 组装 XMindTestCase
        importance_map = {"high": 1, "medium": 2, "low": 3}
        execution_type = 1 # 默认手工
        
        case = XMindTestCase(
            name=case_name,
            summary=tc.description or "",
            preconditions=tc.preconditions or "",
            importance=importance_map.get(tc.priority, 2),
            execution_type=execution_type,
            steps=steps,
            tc_id=str(tc.id)
        )

        if not target_suite.testcase_list:
            target_suite.testcase_list = []
        target_suite.testcase_list.append(case)

    # 7️⃣ 生成 XMind ZIP
    xmind_bytes = write_xmind_zip([root_suite])

    # 8️⃣ 下载返回
    filename = f"{project.name}_测试用例_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xmind"
    encoded_filename = quote(filename)

    return StreamingResponse(
        xmind_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/projects/{project_id}/test-cases/template")
async def download_import_template(
    project_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """下载测试用例导入模板"""
    import pandas as pd
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from urllib.parse import quote

    # 定义表头
    headers = [
        "所属模块", "用例标题", "前置条件", "测试步骤", "预期结果",
        "优先级(高/中/低)", "设计方法", "测试分类"
    ]

    # 创建示例数据
    example_data = [
        {
            "所属模块": "用户管理",
            "用例标题": "用户登录成功",
            "前置条件": "用户已注册且状态正常",
            "测试步骤": "1. 输入正确的用户名\n2. 输入正确的密码\n3. 点击登录按钮",
            "预期结果": "1. 登录成功\n2. 跳转至首页",
            "优先级(高/中/低)": "高",
            "设计方法": "功能测试",
            "测试分类": "功能测试"
        }
    ]

    df = pd.DataFrame(example_data, columns=headers)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='导入模板')

        # 调整列宽
        worksheet = writer.sheets['导入模板']
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
            worksheet.column_dimensions[chr(65 + i)].width = column_len

    output.seek(0)
    filename = "测试用例导入模板.xlsx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.post("/projects/{project_id}/test-cases/import")
async def import_test_cases(
    project_id: int,
    file: UploadFile,
    auto_optimize: bool = Form(False),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """从 Excel 或 XMind 导入测试用例"""
    import pandas as pd
    import os
    import tempfile
    from io import BytesIO
    from app.models.module import Module
    from app.lib.xmind2testcase.utils import get_xmind_testsuites

    # 1️⃣ 检查权限
    check_project_edit_permission(project_id, current_user, db)

    temp_path = None
    try:
        # 2️⃣ 解析数据
        imported_data = [] # List of dict: {path, title, preconditions, steps, expected, priority, method, category}

        if file.filename.endswith(('.xlsx', '.xls')):
            content = await file.read()
            df = pd.read_excel(BytesIO(content))
            required_columns = ["所属模块", "用例标题"]
            if not all(col in df.columns for col in required_columns):
                raise HTTPException(status_code=400, detail=f"文件缺少必要列: {', '.join(required_columns)}")
            
            for _, row in df.iterrows():
                title = str(row.get("用例标题", "")).strip()
                if not title or title == "nan": continue
                
                path = str(row.get("所属模块", "未分类")).strip()
                if path == "nan": path = "未分类"
                
                imported_data.append({
                    "path": path,
                    "title": title,
                    "preconditions": str(row.get("前置条件", "")) if str(row.get("前置条件", "")) != "nan" else "",
                    "steps_raw": str(row.get("测试步骤", "")),
                    "expected_raw": str(row.get("预期结果", "")),
                    "priority": str(row.get("优先级(高/中/低)", "中")).strip(),
                    "design_method": str(row.get("设计方法", "")) if str(row.get("设计方法", "")) != "nan" else "",
                    "test_category": str(row.get("测试分类", "")) if str(row.get("测试分类", "")) != "nan" else ""
                })

        elif file.filename.endswith('.xmind'):
            # 保存到临时文件
            suffix = ".xmind"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                temp_path = tmp.name
            
            # 解析 XMind
            testsuites = get_xmind_testsuites(temp_path)
            
            def flatten_suite(suite, current_path):
                # suite 是 metadata.TestSuite 对象
                # current_path 是列表
                
                # 处理当前层级的用例
                if suite.testcase_list:
                    path_str = " / ".join(current_path) if current_path else "未分类"
                    for tc in suite.testcase_list:
                        # tc 是 metadata.TestCase 对象
                        # 转换步骤
                        steps = []
                        if tc.steps:
                            for s in tc.steps:
                                steps.append({
                                    "action": s.actions,
                                    "expected": s.expectedresults
                                })
                        
                        p_map = {1: "高", 2: "中", 3: "低"}
                        imported_data.append({
                            "path": path_str,
                            "title": tc.name,
                            "preconditions": tc.preconditions or "",
                            "test_category": "functional",
                            "test_steps": steps, # XMind 直接解析出了结构化步骤
                            "priority": p_map.get(tc.importance, "中"),
                            "design_method": "scenario"
                        })
                
                # 递归处理子套件
                if suite.sub_suites:
                    for sub in suite.sub_suites:
                        flatten_suite(sub, current_path + [sub.name])

            for ts in testsuites:
                # TS 根节点通常是文件名或画布名，如果不想要它可以直接传子节点
                if ts.sub_suites:
                    for sub in ts.sub_suites:
                        flatten_suite(sub, [sub.name])
                else:
                    # 只有根节点下有案例的情况
                    flatten_suite(ts, [] )

        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式")

        # 3️⃣ 合并标题一致的用例
        merged_map = {} # (path, title) -> data_dict
        for item in imported_data:
            key = (item["path"], item["title"])
            if key not in merged_map:
                merged_map[key] = item
            else:
                target = merged_map[key]
                # 合并前置条件
                if item.get("preconditions") and item["preconditions"] not in target["preconditions"]:
                    target["preconditions"] += "\n" + item["preconditions"]
                
                # 合并步骤
                if "test_steps" in item:
                    if "test_steps" not in target: target["test_steps"] = []
                    target["test_steps"].extend(item["test_steps"])
                else:
                    # Excel 导入的 raw 字段合并
                    target["steps_raw"] = (target.get("steps_raw", "") + "\n" + item.get("steps_raw", "")).strip()
                    target["expected_raw"] = (target.get("expected_raw", "") + "\n" + item.get("expected_raw", "")).strip()

        # 4️⃣ 预加载/创建模块
        existing_modules = db.query(Module).filter(Module.project_id == project_id).all()
        module_map = {m.name: m.id for m in existing_modules}

        def get_or_create_module(name):
            name = name.strip()
            if not name: name = "未分类"
            if name in module_map:
                return module_map[name]
            
            # 创建新模块
            new_mod = Module(name=name, project_id=project_id)
            db.add(new_mod)
            db.flush() # 获取 ID
            module_map[name] = new_mod.id
            return new_mod.id

        # 5️⃣ 写入数据库
        imported_count = 0
        for data in merged_map.values():
            module_id = get_or_create_module(data["path"])
            
            priority_map = {"高": "high", "中": "medium", "低": "low"}
            priority = priority_map.get(data["priority"], "medium")

            # 处理步骤（针对 Excel 的解析逻辑，XMind 已在前面处理）
            test_steps = data.get("test_steps", [])
            if not test_steps and data.get("steps_raw"):
                # 复用原来的 Excel 解析逻辑
                import re
                steps_text = str(data["steps_raw"])
                expected_text = str(data.get("expected_raw", ""))
                step_pattern = re.compile(r'(\d+)\.\s*')
                step_parts = step_pattern.split(steps_text)
                expected_parts = step_pattern.split(expected_text)
                
                step_dict = {}
                for i in range(1, len(step_parts) - 1, 2):
                    num = step_parts[i]
                    content = step_parts[i+1].strip() if i+1 < len(step_parts) else ""
                    step_dict[num] = content
                
                expected_dict = {}
                for i in range(1, len(expected_parts) - 1, 2):
                    num = expected_parts[i]
                    content = expected_parts[i+1].strip() if i+1 < len(expected_parts) else ""
                    expected_dict[num] = content
                
                if step_dict:
                    for num in sorted(step_dict.keys(), key=lambda x: int(x)):
                        test_steps.append({"action": step_dict[num], "expected": expected_dict.get(num, "")})
                else:
                    test_steps = [{"action": steps_text, "expected": expected_text}]

            # 检查是否存在同名用例，实现覆盖逻辑
            existing_case = db.query(TestCase).filter(
                TestCase.project_id == project_id,
                TestCase.module_id == module_id,
                TestCase.title == data["title"]
            ).first()

            if existing_case:
                # 覆盖逻辑
                existing_case.preconditions = data.get("preconditions")
                existing_case.test_steps = test_steps
                existing_case.priority = priority
                existing_case.design_method = data.get("design_method")
                existing_case.test_category = data.get("test_category")
                existing_case.status = TestCaseStatus.DRAFT # 覆盖后重置为草稿
            else:
                # 创建新用例
                new_case = TestCase(
                    title=data["title"],
                    module_id=module_id,
                    project_id=project_id,
                    preconditions=data.get("preconditions"),
                    test_steps=test_steps,
                    priority=priority,
                    design_method=data.get("design_method"),
                    test_category=data.get("test_category"),
                    created_by=current_user.id,
                    status=TestCaseStatus.DRAFT
                )
                db.add(new_case)
            
            imported_count += 1

        db.commit()
        return {"success": True, "imported_count": imported_count, "message": f"成功导入 {imported_count} 条测试用例"}

    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
