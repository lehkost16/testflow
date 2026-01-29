<template>
  <div class="archive-detail p-6 min-h-screen bg-gray-50 text-black">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
      <div class="flex items-center gap-4">
        <button @click="router.back()" class="p-2 hover:bg-gray-200 rounded-xl transition-colors">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <div>
           <h1 class="text-2xl font-bold">{{ archiveName }}</h1>
           <p class="text-sm text-gray-500">归档详情</p>
        </div>
      </div>
      
      <el-button :loading="exporting" @click="handleExport('markdown')">
        <el-icon class="mr-2"><Download /></el-icon>
        导出执行结果
      </el-button>
    </div>

       <div class="grid grid-cols-2 md:grid-cols-6 gap-4 w-full">
          <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-gray-500 mb-1">总计</div>
             <div class="text-2xl font-bold text-gray-800">{{ stats.total }}</div>
          </div>
          <div class="bg-white p-4 rounded-xl border border-green-100 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-green-600 mb-1">通过</div>
             <div class="text-2xl font-bold text-green-600">{{ stats.passed }}</div>
          </div>
          <div class="bg-white p-4 rounded-xl border border-red-100 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-red-600 mb-1">失败</div>
             <div class="text-2xl font-bold text-red-600">{{ stats.failed }}</div>
          </div>
          <div class="bg-white p-4 rounded-xl border border-orange-100 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-orange-600 mb-1">阻塞</div>
             <div class="text-2xl font-bold text-orange-600">{{ stats.blocked }}</div>
          </div>
          <div class="bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-gray-500 mb-1">跳过</div>
             <div class="text-2xl font-bold text-gray-400">{{ stats.skipped }}</div>
          </div>
          <div class="bg-white p-4 rounded-xl border border-blue-50 shadow-sm flex flex-col justify-center items-center">
             <div class="text-xs text-blue-600 mb-1">通过率</div>
             <div class="text-2xl font-bold text-blue-600">{{ stats.passRate }}%</div>
          </div>
       </div>

    <!-- Case List -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <el-table :data="testCases" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="module_full_path" label="模块" width="200" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="250" show-overflow-tooltip />
        <el-table-column prop="priority" label="优先级" width="100">
           <template #default="{ row }">
              <span :class="getPriorityClass(row.priority || '')">{{ getPriorityLabel(row.priority || '') }}</span>
           </template>
        </el-table-column>
        <el-table-column prop="execution_status" label="执行结果" width="120">
           <template #default="{ row }">
              <el-tag :type="getStatusType(row.execution_status)">
                {{ getStatusLabel(row.execution_status) }}
              </el-tag>
           </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
             <el-button link type="primary" @click="openRunDrawer(row)">执行/查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Execution Drawer -->
    <el-drawer
      v-model="drawerVisible"
      title="执行测试用例"
      size="50%"
      destroy-on-close
    >
      <div v-if="currentCase" class="h-full flex flex-col bg-white">
        <div class="flex-1 overflow-y-auto px-1 py-2">
             <!-- Title Section -->
             <div class="mb-6 border-l-4 border-blue-500 pl-4 py-1">
               <h2 class="text-xl font-bold text-gray-900">{{ currentCase.title }}</h2>
               <div class="mt-2 flex items-center gap-4 text-sm text-gray-500">
                 <el-tag size="small" effect="plain">{{ currentCase.module_full_path }}</el-tag>
                 <el-tag size="small" :type="getPriorityClass(currentCase.priority || '').includes('red') ? 'danger' : 'info'">
                    {{ getPriorityLabel(currentCase.priority || '') }}
                 </el-tag>
               </div>
             </div>

             <!-- Info Section -->
             <div class="grid grid-cols-1 gap-4 mb-6">
                <div v-if="currentCase.description" class="bg-gray-50 p-4 rounded-xl border border-gray-100">
                    <div class="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">描述</div>
                    <div class="text-sm text-gray-700 leading-relaxed">{{ currentCase.description }}</div>
                </div>
                <div v-if="currentCase.preconditions" class="bg-blue-50 p-4 rounded-xl border border-blue-100">
                    <div class="text-xs font-bold text-blue-500 uppercase tracking-wide mb-2">前置条件</div>
                    <div class="text-sm text-gray-700 leading-relaxed">{{ currentCase.preconditions }}</div>
                </div>
             </div>

             <!-- Steps Execution -->
             <div class="mb-8">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="font-bold text-lg text-gray-800 flex items-center gap-2">
                        <el-icon><List /></el-icon> 测试步骤
                    </h3>
                    <span class="text-xs text-gray-400">共 {{ currentCase.test_steps?.length || 0 }} 步</span>
                </div>
                
                <div class="space-y-4">
                   <div 
                     v-for="(step, idx) in currentCase.test_steps" 
                     :key="idx" 
                     class="group border border-gray-200 rounded-xl p-5 hover:shadow-md transition-all duration-200 bg-white"
                     :class="{'border-blue-200 ring-2 ring-blue-50': currentExecution.step_results[String(idx+1)].status !== 'skipped'}"
                   >
                     <div class="flex justify-between items-start mb-4">
                        <div class="flex items-center gap-3">
                            <span class="flex items-center justify-center w-6 h-6 rounded-full bg-gray-100 text-xs font-bold text-gray-500 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                                {{ idx + 1 }}
                            </span>
                            <span class="text-sm font-medium text-gray-900">执行步骤</span>
                        </div>
                        
                        <!-- Step Status -->
                        <div class="scale-90 origin-right">
                           <el-radio-group v-model="currentExecution.step_results[String(idx+1)].status" size="small">
                              <el-radio-button label="passed"><el-icon><Check /></el-icon> 通过</el-radio-button>
                              <el-radio-button label="failed" class="!text-red-500"><el-icon><Close /></el-icon> 失败</el-radio-button>
                              <el-radio-button label="blocked"><el-icon><Remove /></el-icon> 阻塞</el-radio-button>
                              <el-radio-button label="skipped">跳过</el-radio-button>
                           </el-radio-group>
                        </div>
                     </div>
                     
                     <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 text-sm">
                        <div class="bg-gray-50 p-3 rounded-lg border border-gray-100">
                           <div class="text-xs text-gray-400 mb-1">操作步骤</div>
                           <div class="text-gray-700 leading-normal">{{ step.action }}</div>
                        </div>
                        <div class="bg-gray-50 p-3 rounded-lg border border-gray-100">
                           <div class="text-xs text-gray-400 mb-1">预期结果</div>
                           <div class="text-gray-700 leading-normal">{{ step.expected }}</div>
                        </div>
                     </div>
                     
                     <!-- Actual Result Input -->
                     <transition name="el-fade-in">
                         <div v-if="currentExecution.step_results[String(idx+1)].status !== 'passed' && currentExecution.step_results[String(idx+1)].status !== 'skipped'" class="mt-3">
                            <el-input 
                              v-model="currentExecution.step_results[String(idx+1)].actual" 
                              placeholder="请输入实际结果描述..."
                              type="textarea"
                              :rows="2"
                              class="w-full"
                            />
                         </div>
                     </transition>
                   </div>
                </div>
             </div>
             
             <!-- Overall Result -->
             <div class="bg-gray-50 rounded-2xl p-6 border border-gray-200">
                 <h3 class="font-bold text-lg text-gray-800 mb-4 flex items-center gap-2">
                     <el-icon><Trophy /></el-icon> 总体执行结果
                 </h3>
                 <el-form label-position="top">
                    <el-form-item>
                      <div class="w-full flex justify-center">
                          <el-radio-group v-model="currentExecution.status" size="large">
                              <el-radio-button label="passed" class="!px-6">✅ 通过</el-radio-button>
                              <el-radio-button label="failed" class="!px-6 !text-red-600">❌ 失败</el-radio-button>
                              <el-radio-button label="blocked" class="!px-6">🚫 阻塞</el-radio-button>
                              <el-radio-button label="skipped" class="!px-6">⏭️ 跳过</el-radio-button>
                          </el-radio-group>
                      </div>
                    </el-form-item>
                    <el-form-item label="执行备注">
                       <el-input 
                         v-model="currentExecution.comment" 
                         type="textarea" 
                         :rows="3" 
                         placeholder="添加本次执行的总体备注..."
                        />
                    </el-form-item>
                 </el-form>
             </div>
        </div>
        
        <div class="mt-4 pt-4 border-t border-gray-100 flex justify-end gap-3 bg-white">
           <el-button size="large" @click="drawerVisible = false">取消</el-button>
           <el-button size="large" type="primary" bg class="bg-black text-white hover:bg-gray-800 border-none px-8" @click="saveExecution" :loading="saving">
              保存结果
           </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, ArrowDown } from '@element-plus/icons-vue'
import { archiveApi, type ArchivedTestCase } from '@/api/archive'

const route = useRoute()
const router = useRouter()
const archiveId = Number(route.params.archiveId)
// We might need projectId for API calls if we structured api that way, 
// strictly speaking archiveApi uses archiveId for getArchiveCases, creating requires projectId.
// archiveApi.getArchives(projectId). We need to fetch archive details to get name.
// But we don't have a single "getArchive" endpoint in my previous file?
// Ah, `getArchives` returns list. I can filter.
// Or add `getArchive(id)` to backend.
// For now, I'll fetch list and find. Or minimal redundant call.

const loading = ref(false)
const testCases = ref<ArchivedTestCase[]>([])
const archiveName = ref('归档详情')

// Drawer & Execution
const drawerVisible = ref(false)
const currentCase = ref<ArchivedTestCase | null>(null)
const currentExecution = reactive({
   status: 'skipped',
   comment: '',
   step_results: {} as Record<string, { status: string, actual: string }>
})
const saving = ref(false)

// Init
const loadData = async () => {
   loading.value = true
   try {
     const cases = await archiveApi.getArchiveCases(archiveId)
     testCases.value = cases
     
     // Retrieve archive name if possible
     // Since we are in the context of a project, maybe fetch project archives?
     const projectId = route.params.projectId
     if (projectId) {
         const archives = await archiveApi.getArchives(Number(projectId))
         const arc = archives.find(a => a.id === archiveId)
         if (arc) archiveName.value = arc.name
     }
   } catch (error) {
     ElMessage.error('加载数据失败')
   } finally {
     loading.value = false
   }
}

const stats = computed(() => {
    const total = testCases.value.length
    const passed = testCases.value.filter(c => c.execution_status === 'passed').length
    const failed = testCases.value.filter(c => c.execution_status === 'failed').length
    const blocked = testCases.value.filter(c => c.execution_status === 'blocked').length
    const skipped = testCases.value.filter(c => c.execution_status === 'skipped').length
    
    return {
        total, passed, failed, blocked, skipped,
        passRate: total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0'
    }
})

// Helpers
const getPriorityLabel = (p: string) => {
    const map: any = { high: '高', medium: '中', low: '低' }
    return map[p] || p
}
const getPriorityClass = (p: string) => {
    const map: any = { high: 'text-red-500 font-bold', medium: 'text-yellow-600', low: 'text-gray-500' }
    return map[p] || ''
}
const getStatusLabel = (s: string) => {
    const map: any = { passed: '通过', failed: '失败', blocked: '阻塞', skipped: '跳过', in_progress: '进行中' }
    return map[s] || s || '未执行'
}
const getStatusType = (s: string) => {
    const map: any = { passed: 'success', failed: 'danger', blocked: 'warning', skipped: 'info' }
    return map[s] || 'info'
}

// Run Interaction
const openRunDrawer = (row: ArchivedTestCase) => {
    currentCase.value = row
    currentExecution.status = row.execution_status || 'skipped'
    currentExecution.comment = row.execution_comment || ''
    
    // Init step results
    currentExecution.step_results = {}
    if (row.test_steps) {
        row.test_steps.forEach((_, idx) => {
            const stepNum = String(idx + 1)
            const saved = row.step_execution_results?.[stepNum]
            currentExecution.step_results[stepNum] = {
                status: saved?.status || 'skipped',
                actual: saved?.actual || ''
            }
        })
    }
    
    drawerVisible.value = true
}

const saveExecution = async () => {
   if (!currentCase.value) return
   saving.value = true
   try {
      const updated = await archiveApi.updateExecution(currentCase.value.id, {
          status: currentExecution.status,
          comment: currentExecution.comment,
          step_results: currentExecution.step_results
      })
      
      // Update local list
      const idx = testCases.value.findIndex(c => c.id === updated.id)
      if (idx !== -1) {
          testCases.value[idx] = updated
      }
      
      ElMessage.success('保存成功')
      drawerVisible.value = false
   } catch (error: any) {
      ElMessage.error('保存失败')
   } finally {
      saving.value = false
   }
}

// Export
const exporting = ref(false)
const handleExport = async (format: string) => {
    exporting.value = true
    try {
       const blob = await archiveApi.exportArchive(archiveId, format as 'xmind'|'csv')
       const url = window.URL.createObjectURL(blob)
       const link = document.createElement('a')
       link.href = url
       
       const ext = format === 'xmind' ? 'xmind' : (format === 'markdown' ? 'md' : 'csv')
       const filename = `${archiveName.value}_导出.${ext}`
       link.download = filename
       document.body.appendChild(link)
       link.click()
       document.body.removeChild(link)
       window.URL.revokeObjectURL(url)
       ElMessage.success('导出成功')
    } catch (error) {
       ElMessage.error('导出失败')
    } finally {
       exporting.value = false
    }
}

onMounted(() => {
   loadData()
})
</script>

<style scoped>
/* Element UI Overrides if needed */
</style>
