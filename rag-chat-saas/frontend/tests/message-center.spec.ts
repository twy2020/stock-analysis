import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import FeedbackBubble from '../src/components/FeedbackBubble.vue'
import { useChatStore } from '../src/stores/chat'

beforeEach(()=>{
 setActivePinia(createPinia())
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
})
afterEach(()=>vi.unstubAllGlobals())
const row={id:'ticket',ticketNumber:'FB-20260929-12345678',username:'member',comment:'页面不能翻页',status:'REVIEWING',createdAt:'2026-09-29T00:00:00Z',updatedAt:'2026-09-29T00:00:00Z',latestReplyId:1,unread:true,imageCount:0,conversationTitle:'问题'}
it('opens an unread ticket, reads replies, continues feedback and respects closure',async()=>{
 let closed=false;const replies=[{id:1,username:'admin',role:'ADMIN',kind:'REPLY',body:'请提供页码',createdAt:row.createdAt}]
 vi.stubGlobal('fetch',vi.fn(async(url:string,options:any)=>{
  if(url.includes('/unread'))return Response.json({system:0,feedback:1})
  if(url.endsWith('/replies')) {replies.push({id:2,username:'member',role:'USER',kind:'REPLY',body:JSON.parse(options.body).body,createdAt:row.createdAt});closed=true}
  if(url.endsWith('/read'))return new Response(null,{status:204})
  if(url.includes('/feedback/ticket'))return Response.json({...row,status:closed?'RESOLVED':'REVIEWING',images:[],snapshot:{messages:[]},replies})
  if(url.includes('/feedback?'))return Response.json({items:[row],total:1})
  return Response.json({items:[],total:0})
 }))
 const wrapper=mount(FeedbackBubble,{props:{draft:''}});await flushPromises()
 expect(wrapper.find('.notification-dot').exists()).toBe(true)
 await wrapper.get('[aria-label="消息中心"]').trigger('click');await flushPromises()
 await wrapper.get('[data-section="history"]').trigger('click');await flushPromises()
 await wrapper.get('[data-ticket="ticket"]').trigger('click');await flushPromises()
 expect(wrapper.text()).toContain('请提供页码')
 await wrapper.get('[aria-label="补充反馈"]').setValue('第 12 页')
 await wrapper.get('.ticket-reply-form').trigger('submit');await flushPromises()
 expect(wrapper.text()).toContain('第 12 页')
 expect(wrapper.find('.ticket-reply-form').exists()).toBe(false)
 expect(wrapper.text()).toContain('工单已关闭')
 useChatStore().resetForSession();await flushPromises()
 expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
 expect(wrapper.text()).not.toContain('第 12 页')
 wrapper.unmount()
})
