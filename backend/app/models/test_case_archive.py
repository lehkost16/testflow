from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.database import Base
from app.models.testcase import Priority, TestMethod, ExecutionStatus

class ArchiveStatus(str, enum.Enum):
    """归档状态"""
    ACTIVE = "active"
    CLOSED = "closed"

class ProjectArchive(Base):
    """项目用例归档模型"""
    __tablename__ = "project_archives"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ArchiveStatus] = mapped_column(Enum(ArchiveStatus), default=ArchiveStatus.ACTIVE)
    
    # 归档信息
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    project: Mapped["Project"] = relationship("Project", backref="archives")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    test_cases: Mapped[List["ArchivedTestCase"]] = relationship("ArchivedTestCase", back_populates="archive", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"ProjectArchive(id={self.id!r}, name={self.name!r}, project_id={self.project_id!r})"


class ArchivedTestCase(Base):
    """归档的测试用例模型（包含执行结果）"""
    __tablename__ = "archived_test_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    archive_id: Mapped[int] = mapped_column(ForeignKey("project_archives.id", ondelete="CASCADE"), index=True)
    original_case_id: Mapped[Optional[int]] = mapped_column(Integer, index=True) # 记录原始ID，但不做外键约束，防止原始用例删除影响归档
    
    # --- 快照字段 (创建归档时复制) ---
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    preconditions: Mapped[Optional[str]] = mapped_column(Text)
    test_steps: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON) # 步骤快照
    expected_result: Mapped[Optional[str]] = mapped_column(Text)
    
    module_name: Mapped[Optional[str]] = mapped_column(String(100)) # 记录当时的模块名（扁平化存储，因为模块结构可能变）
    module_full_path: Mapped[Optional[str]] = mapped_column(String(500)) # 记录模块完整路径，方便展示
    
    priority: Mapped[str] = mapped_column(String(20))
    test_category: Mapped[Optional[str]] = mapped_column(String(50))
    design_method: Mapped[Optional[str]] = mapped_column(String(50))
    
    # --- 执行结果字段 (归档后可编辑) ---
    execution_status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus), default=ExecutionStatus.SKIPPED)
    execution_comment: Mapped[Optional[str]] = mapped_column(Text)
    step_execution_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON) 
    # 格式: { "step_index_1": {"status": "passed", "actual": "xxx"}, ... }
    
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    
    # 关系
    archive: Mapped["ProjectArchive"] = relationship("ProjectArchive", back_populates="test_cases")
    updater: Mapped["User"] = relationship("User", foreign_keys=[updated_by])

    def __repr__(self) -> str:
        return f"ArchivedTestCase(id={self.id!r}, title={self.title!r}, status={self.execution_status!r})"
