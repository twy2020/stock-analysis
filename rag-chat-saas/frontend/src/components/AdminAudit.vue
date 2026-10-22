<script setup lang="ts">
import { onMounted, onDeactivated, ref, watch } from 'vue'
import { RefreshCw, X } from 'lucide-vue-next'
import { api } from '../api/client'
type Row={id:string;kind:string;action:string;status:string;username:string;runId:string|null;conversationId:string|null;latencyMs:number|null;createdAt:string;details:Record<string,any>}
type Result={items:Row[];total:number;pageSize:number;summary:{counts:Record<string,number>;averageMs:number}}
const emit=defineEmits<{feedback:[id:string]}>()
const props=withDefaults(defineProps<{active?:boolean}>(),{active:true})
const kind=ref('model'),status=ref(''),q=ref(''),from=ref(''),to=ref(''),action=ref(''),run=ref(''),rotated=ref(false)
const page=ref(1),loading=ref(false),error=ref(''),selected=ref<Row|null>(null)
const result=ref<Result>({items:[],total:0,pageSize:30,summary:{counts:{},averageMs:0}})
let sequence=0
const actions:Record<string,string>={
 'chat.answer_failed':'问答异常',
 'chat.completions':'模型调用',list_documents:'读取文档目录',recall:'知识检索',current_time:'获取时间',
 'chat.vote_message':'评价回答','chat.create_run':'发起问答','chat.cancel_run':'停止回复','chat.run_finished':'问答任务结束',
 'auth.login':'登录','auth.register':'注册账号','admin.put_registration_settings':'修改注册设置','auth.logout':'退出登录','auth.change_password':'修改密码',
 'conversations.create_conversation':'新建对话','conversations.update_conversation':'重命名对话','conversations.delete_conversation':'删除对话',
 'feedback.create_feedback':'提交反馈','feedback.update_feedback':'处理反馈',
 'feedback.user_reply':'补充反馈','feedback.admin_reply':'回复工单','message_center.publish':'发布系统消息','message_center.withdraw':'撤回系统消息',
 'admin.put_rag_settings':'修改 RAG 连接','admin.create_provider':'添加供应商','admin.create_account':'添加模型账号',
 'admin.update_account':'修改模型账号','admin.create_user':'创建用户','admin.update_user':'修改用户',
}
const states:Record<string,string>={SUCCEEDED:'成功',FAILED:'失败',RUNNING:'执行中',CANCELLED:'已取消',INTERRUPTED:'服务中断'}
const errors:Record<string,string>={AUTHENTICATION:'供应商认证失败',RATE_LIMIT:'供应商限流',TIMEOUT:'请求超时',CONNECTION:'连接失败',UPSTREAM:'供应商响应异常',EMPTY_RESPONSE:'模型未返回内容',INTERNAL:'内部错误',CANCELLED:'已停止',INVALID_ARGUMENTS:'工具参数无效',RAG_UNAVAILABLE:'检索服务不可用'}
const fields:Record<string,string>={status:'状态',role:'角色',concurrencyLimit:'并发上限',weight:'权重',model:'模型',name:'名称'}
Object.assign(errors,{INVALID_CITATION:'引用校验失败',MODEL_STREAM_INTERRUPTED:'回复流异常',STREAM_INTERRUPTED:'回复未正常结束',TASK_FAILED:'后台任务异常',WORKER_RESTARTED:'服务重启中断',MODEL_UNAVAILABLE:'没有可用模型',INVALID_MODEL_RESPONSE:'模型响应无效',UNKNOWN:'未知异常'})
function label(row:Row){if(row.action==='chat.vote_message')return row.details.vote===1?'点赞':row.details.vote===-1?'点踩':'撤销评价';return row.details.operation||actions[row.action]||row.action}
function date(value:string){return new Date(value).toLocaleString('zh-CN',{hour12:false})}
function ms(value:number|null|undefined){return value==null?'—':`${(value/1000).toFixed(2)} 秒`}
function description(row:Row){const d=row.details;return errors[d.errorCategory]||d.errorCategory||d.errorCode||d.conversationTitle||d.name||d.username||'—'}
async function load(reset=false){
 const start=from.value?new Date(from.value).getTime():null,end=to.value?new Date(to.value).getTime():null
 if((start!==null&&!Number.isFinite(start))||(end!==null&&!Number.isFinite(end))||(start!==null&&end!==null&&start>end)){error.value='请填写有效时间，开始时间不能晚于结束时间';return}
 if(reset)page.value=1
 const rev=++sequence;loading.value=true;error.value=''
 const params=new URLSearchParams({kind:kind.value,page:String(page.value),q:q.value,status:status.value,action:action.value,run_id:run.value})
 if(from.value)params.set('from',new Date(from.value).toISOString())
 if(to.value)params.set('to',new Date(to.value).toISOString())
 if(rotated.value&&kind.value==='model')params.set('rotated','true')
 try{const data=await api<Result>('/api/v1/admin/audit?'+params);if(rev===sequence)result.value=data}
 catch(e){if(rev===sequence)error.value=e instanceof Error?e.message:'加载失败'}
 finally{if(rev===sequence)loading.value=false}
}
watch(kind,()=>{action.value='';run.value='';rotated.value=false;void load(true)})
onMounted(()=>load())
onDeactivated(()=>{selected.value=null})
watch(()=>props.active,active=>{if(!active)selected.value=null})
function resetFilters(){q.value='';status.value='';from.value='';to.value='';action.value='';run.value='';rotated.value=false;void load(true)}
function trace(row:Row){run.value=row.runId||'';selected.value=null;void load(true)}
</script>
<template>
 <section class="audit-view">
  <div class="audit-kinds"><button v-for="item in [{id:'model',text:'模型调用'},{id:'tool',text:'工具与检索'},{id:'exception',text:'问答异常'},{id:'activity',text:'用户与管理动态'}]" :class="{active:kind===item.id}" @click="kind=item.id">{{item.text}}</button></div>
  <form class="audit-filters" @submit.prevent="load(true)">
   <input v-model="q" aria-label="搜索日志" placeholder="用户、模型、账号或会话" />
   <select v-model="status" aria-label="执行状态"><option value="">全部状态</option><option v-for="(text,value) in states" :value="value">{{text}}</option></select>
   <select v-if="kind==='activity'" v-model="action" aria-label="操作类型"><option value="">全部操作</option><option v-for="(text,value) in actions" v-show="value.includes('.') && value!=='chat.completions'" :value="value">{{text}}</option></select>
   <label>开始<input v-model="from" type="datetime-local" /></label><label>结束<input v-model="to" type="datetime-local" /></label>
   <label v-if="kind==='model'"><input v-model="rotated" type="checkbox" />仅故障切换</label>
   <button class="compact-button" :disabled="loading">筛选</button><button class="text-button" type="button" :disabled="loading" @click="resetFilters">重置</button><button class="icon-button" type="button" aria-label="刷新日志" :disabled="loading" @click="load()"><RefreshCw :size="16" /></button>
  </form>
  <div v-if="run" class="audit-scope">当前仅显示同一轮任务<button class="text-button" @click="run='';load(true)">清除</button></div>
  <div class="audit-summary"><span>共 <b>{{result.total}}</b> 条</span><span>成功 {{result.summary.counts.SUCCEEDED||0}}</span><span>失败 {{result.summary.counts.FAILED||0}}</span><span v-if="kind!=='activity'">平均耗时 {{ms(result.summary.averageMs)}}</span></div>
  <p v-if="error" class="admin-message error" role="alert">{{error}}</p>
  <div class="data-table-wrap audit-table-wrap" :aria-busy="loading"><table class="data-table audit-table">
   <colgroup><col style="width:172px"/><col style="width:130px"/><col style="width:180px"/><col style="width:220px"/><col style="width:96px"/><col style="width:110px"/><col style="width:240px"/><col style="width:80px"/></colgroup>
   <thead><tr><th>时间</th><th>用户</th><th>{{kind==='model'?'供应商 / 账号':'操作'}}</th><th>{{kind==='model'?'模型':'关联内容'}}</th><th>状态</th><th>耗时</th><th>{{kind==='model'?'调度 / 错误':'记录'}}</th><th>操作</th></tr></thead>
   <tbody><tr v-for="row in result.items" :key="row.id"><td>{{date(row.createdAt)}}</td><td :title="row.username">{{row.username}}</td><td :title="kind==='model'?`${row.details.provider} / ${row.details.account}`:label(row)">{{kind==='model'?`${row.details.provider} / ${row.details.account}`:label(row)}}</td><td :title="row.details.model||row.details.conversationTitle||row.details.name">{{row.details.model||row.details.conversationTitle||row.details.name||'—'}}</td><td><span class="status" :class="row.status.toLowerCase()">{{states[row.status]||row.status}}</span></td><td>{{ms(row.latencyMs)}}</td><td :title="description(row)">{{row.details.rotated?`故障切换 · ${row.details.previousAccount} → ${row.details.account}`:kind==='model'&&!row.details.errorCategory?'按权重调度':description(row)}}</td><td><button class="text-button" @click="selected=row">详情</button></td></tr>
   <tr v-if="!result.items.length"><td colspan="8" class="table-empty">{{loading?'正在加载':'暂无符合条件的记录'}}</td></tr></tbody>
  </table></div>
  <footer class="audit-pagination"><span>第 {{page}} / {{Math.max(1,Math.ceil(result.total/result.pageSize))}} 页</span><button class="compact-button" :disabled="page<=1||loading" @click="page--;load()">上一页</button><button class="compact-button" :disabled="page*result.pageSize>=result.total||loading" @click="page++;load()">下一页</button></footer>
  <p class="audit-retention">逐次调用与操作记录从本次更新起采集；已删除会话的审计记录仍保留。不会记录密钥或密码。</p>
 </section>
 <div v-if="selected" class="modal-scrim" @keydown.esc="selected=null"><section class="admin-modal audit-detail" role="dialog" aria-modal="true" aria-label="审计详情"><header><h2>{{label(selected)}}</h2><button class="icon-button" aria-label="关闭详情" @click="selected=null"><X :size="18"/></button></header><div class="audit-detail-body">
  <dl><dt>时间</dt><dd>{{date(selected.createdAt)}}</dd><dt>用户</dt><dd>{{selected.username}}</dd><dt>状态</dt><dd>{{states[selected.status]}}</dd><dt>总耗时</dt><dd>{{ms(selected.latencyMs)}}</dd>
  <template v-if="selected.kind==='model'"><dt>供应商 / 账号</dt><dd>{{selected.details.provider}} / {{selected.details.account}}</dd><dt>模型</dt><dd>{{selected.details.model}}</dd><dt>首个输出</dt><dd>{{ms(selected.details.firstTokenMs)}}</dd><dt>输入 / 输出 Token</dt><dd>{{selected.details.promptTokens??'未返回'}} / {{selected.details.completionTokens??'未返回'}}</dd><dt>调度</dt><dd>{{selected.details.rotated?`由 ${selected.details.previousAccount} 切换，原因：${errors[selected.details.rotationReason]||selected.details.rotationReason}`:'按权重选择可用账号'}}</dd></template>
  <dt>HTTP 状态</dt><dd>{{selected.details.httpStatus??'—'}}</dd><dt v-if="selected.details.errorCategory">错误原因</dt><dd v-if="selected.details.errorCategory">{{errors[selected.details.errorCategory]||selected.details.errorCategory}}</dd>
  <dt v-if="selected.details.resultCount!=null">返回结果</dt><dd v-if="selected.details.resultCount!=null">{{selected.details.resultCount}} 条</dd></dl>
  <template v-if="selected.kind==='exception'"><h3>失败现场</h3><dl><dt>错误代码</dt><dd>{{selected.details.errorCode}}</dd><dt>生成状态</dt><dd>{{selected.details.generationCompleted === true ? '模型输出已结束，后续处理失败' : selected.details.generationCompleted === false ? '模型输出未结束' : '未记录'}}</dd><dt>本轮来源数</dt><dd>{{selected.details.sourceCount??'未记录'}}</dd><dt>无效引用编号</dt><dd>{{selected.details.invalidLabels?.join('、')||'—'}}</dd><dt>最后阶段</dt><dd>{{selected.details.lastStage||'—'}}</dd><dt>供应商 / 账号</dt><dd>{{selected.details.provider||'—'}} / {{selected.details.account||'—'}}</dd><dt>回复长度</dt><dd>{{selected.details.answerLength??0}} 字符{{selected.details.snapshotTruncated?'（快照已截取前 4000 字符）':''}}</dd></dl><details v-if="selected.details.recentEvents?.length"><summary>最近执行事件</summary><p v-for="(item,index) in selected.details.recentEvents" :key="index">{{item.stage}} · {{item.tool||item.status||'—'}} · {{ms(item.elapsedMsTotal)}}</p></details></template>
  <template v-if="selected.details.question"><h3>用户问题</h3><p>{{selected.details.question}}</p></template><template v-if="selected.details.answer"><h3>{{selected.kind==='exception'?'异常时的回答快照':'评价时的回答快照'}}</h3><p>{{selected.details.answer}}</p></template>
  <template v-if="selected.details.comment"><h3>反馈意见</h3><p>{{selected.details.comment}}</p><p>附图 {{selected.details.imageCount||0}} 张</p></template>
  <template v-if="selected.details.changes"><h3>配置变更 · {{selected.details.target}}</h3><dl><template v-for="(change,key) in selected.details.changes"><dt>{{fields[String(key)]||key}}</dt><dd>{{change.before}} → {{change.after}}</dd></template></dl></template>
  <button v-if="selected.runId" class="compact-button" @click="trace(selected)">查看本轮同类记录</button><button v-if="selected.details.feedbackId" class="compact-button" @click="emit('feedback',selected.details.feedbackId)">查看用户反馈</button>
  <details><summary>追踪标识</summary><p>记录：{{selected.id}}<br/>任务：{{selected.runId||'—'}}<br/>会话：{{selected.conversationId||'—'}}</p></details>
 </div></section></div>
</template>
