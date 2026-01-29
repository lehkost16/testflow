import api from './index'

export interface ProjectArchive {
  id: number
  name: string
  description: string | null
  status: string
  created_at: string
  created_by_name: string
  case_count: number
}

export interface ArchivedTestCase {
  id: number
  original_case_id: number | null
  title: string
  description: string | null
  preconditions: string | null
  test_steps: any[] | null
  expected_result: string | null
  module_name: string | null
  module_full_path: string | null
  priority: string | null
  test_category: string | null
  design_method: string | null
  execution_status: string
  execution_comment: string | null
  step_execution_results: Record<string, any> | null
  updated_at: string
  updated_by_name: string | null
}

export interface ArchiveCreateRequest {
  name: string
  description?: string
  test_case_ids: number[]
}

export interface ExecutionUpdateRequest {
  status: string
  comment?: string
  step_results?: Record<string, { status: string; actual?: string }>
}

export const archiveApi = {
  // Create archive
  createArchive: (projectId: number, data: ArchiveCreateRequest): Promise<ProjectArchive> => {
    return api.post(`/projects/${projectId}/archives`, data)
  },

  // List archives
  getArchives: (projectId: number): Promise<ProjectArchive[]> => {
    return api.get(`/projects/${projectId}/archives`)
  },

  // List cases in archive
  getArchiveCases: (archiveId: number, params?: { status?: string }): Promise<ArchivedTestCase[]> => {
    return api.get(`/archives/${archiveId}/test-cases`, { params })
  },

  // Update execution result
  updateExecution: (caseId: number, data: ExecutionUpdateRequest): Promise<ArchivedTestCase> => {
    return api.put(`/archives/cases/${caseId}/execution`, data)
  },

  // Export archive
  exportArchive: (archiveId: number, format: 'xmind' | 'csv'): Promise<Blob> => {
    return api.post(`/archives/${archiveId}/export`, 
        { format }, 
        { responseType: 'blob' }
    )
  }
}
