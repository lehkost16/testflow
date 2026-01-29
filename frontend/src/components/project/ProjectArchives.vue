<template>
  <div class="project-archives">
    <!-- Toolbar -->
    <div class="mb-6 flex justify-between items-center">
      <h2 class="text-lg font-bold">归档版本管理</h2>
      <button 
        v-if="canEdit"
        @click="openCreateDialog" 
        class="px-3 py-1.5 bg-black text-white rounded-lg text-sm font-bold hover:bg-gray-800 transition-all flex items-center gap-2"
      >
        <el-icon><Plus /></el-icon>
        新建归档
      </button>
    </div>

    <!-- Archives List -->
    <div v-loading="loading" class="min-h-[200px]">
      <div v-if="archives.length === 0" class="text-center py-10 text-gray-500">
        暂无归档记录
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div 
          v-for="archive in archives" 
          :key="archive.id"
          class="bg-white border border-gray-100 rounded-2xl p-6 hover:shadow-md transition-shadow cursor-pointer relative group"
          @click="goToDetail(archive.id)"
        >
          <div class="flex justify-between items-start mb-4">
            <div>
               <h3 class="font-bold text-gray-900 text-lg">{{ archive.name }}</h3>
               <p class="text-xs text-gray-400 mt-1">创建于 {{ formatDate(archive.created_at) }}</p>
            </div>
            <span 
              class="px-2 py-0.5 rounded-full text-xs font-medium"
              :class="archive.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'"
            >
              {{ archive.status === 'active' ? '活跃' : '已关闭' }}
            </span>
          </div>
          
          <p class="text-sm text-gray-500 mb-4 line-clamp-2 min-h-[40px]">{{ archive.description || '无描述' }}</p>
          
          <div class="flex items-center text-sm text-gray-600 gap-4">
            <div class="flex items-center gap-1">
              <el-icon><List /></el-icon>
              <span>{{ archive.case_count }} 用例</span>
            </div>
            <div class="flex items-center gap-1">
              <el-icon><User /></el-icon>
              <span>{{ archive.created_by_name }}</span>
            </div>
          </div>
          
           <div class="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
              <el-icon class="text-gray-400"><ArrowRight /></el-icon>
           </div>
        </div>
      </div>
    </div>

    <!-- Create Dialog -->
    <el-dialog
      v-model="createDialogVisible"
      title="新建归档"
      width="600px"
      append-to-body
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="归档名称" required>
          <el-input v-model="createForm.name" placeholder="例如：v1.0 发布回归测试" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="可选描述" />
        </el-form-item>
        
        <el-form-item label="选择测试用例" required>
          <div class="border border-gray-200 rounded-lg h-[300px] overflow-y-auto p-2 w-full">
            <div v-if="loadingCases" class="text-center py-4">加载中...</div>
             <el-tree
                v-else
                ref="treeRef"
                :data="treeData"
                show-checkbox
                node-key="key"
                :props="{ label: 'label', children: 'children' }"
                default-expand-all
              />
          </div>
          <p class="text-xs text-gray-400 mt-1">请勾选需要归档的测试用例</p>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" bg class="bg-black text-white border-none hover:bg-gray-800" @click="handleCreate" :loading="creating">
            创建
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, List, User, ArrowRight } from '@element-plus/icons-vue'
import { archiveApi, type ProjectArchive } from '@/api/archive'
import { projectApi } from '@/api/project'

const props = defineProps<{
  projectId: number
  canEdit: boolean
}>()

const router = useRouter()
const loading = ref(false)
const archives = ref<ProjectArchive[]>([])

// Create Dialog
const createDialogVisible = ref(false)
const createForm = ref({
  name: '',
  description: ''
})
const creating = ref(false)
const loadingCases = ref(false)
const treeData = ref<any[]>([])
const treeRef = ref<any>(null)

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString()
}

const loadArchives = async () => {
  loading.value = true
  try {
    archives.value = await archiveApi.getArchives(props.projectId)
  } catch (error) {
    ElMessage.error('加载归档列表失败')
  } finally {
    loading.value = false
  }
}

const openCreateDialog = async () => {
  createForm.value = { name: '', description: '' }
  createDialogVisible.value = true
  loadingCases.value = true
  treeData.value = []
  
  try {
    const data = await projectApi.getProjectTestCases(props.projectId, { view_mode: 'hierarchy' })
    const modules = data.map((mod: any) => ({
      key: `module-${mod.id}`,
      label: mod.name,
      children: (mod.test_cases || []).map((tc: any) => ({
        key: `case-${tc.id}`,
        label: tc.title,
        id: tc.id, // Store actual ID
        isLeaf: true
      }))
    })).filter((node: any) => node.children && node.children.length > 0)
    
    // Wrap in Root Node for "Select All" functionality
    treeData.value = [{
        key: 'root-all',
        label: '全部用例',
        children: modules
    }]
    
  } catch (error) {
    ElMessage.error('加载测试用例失败')
  } finally {
     loadingCases.value = false
  }
}

const handleCreate = async () => {
  if (!createForm.value.name) {
    ElMessage.warning('请输入归档名称')
    return
  }
  
  const checkedNodes = treeRef.value!.getCheckedNodes(true, false) // leafOnly=false to include folders? No, we want cases
  // Actually getCheckedNodes(leafOnly=true) might be better, or filter by key prefix
  
  const caseIds = checkedNodes
    .filter((node: any) => node.key.startsWith('case-'))
    .map((node: any) => node.id)
    
  if (caseIds.length === 0) {
    ElMessage.warning('请至少选择一个测试用例')
    return
  }
  
  creating.value = true
  try {
    await archiveApi.createArchive(props.projectId, {
      name: createForm.value.name,
      description: createForm.value.description,
      test_case_ids: caseIds
    })
    ElMessage.success('归档创建成功')
    createDialogVisible.value = false
    loadArchives()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建归档失败')
  } finally {
    creating.value = false
  }
}

const goToDetail = (archiveId: number) => {
  router.push(`/projects/${props.projectId}/archives/${archiveId}`)
}

onMounted(() => {
  loadArchives()
})
</script>

<style scoped>
.project-archives {
    padding: 20px;
}
</style>
