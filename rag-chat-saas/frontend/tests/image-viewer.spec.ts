import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ImageViewer from '../src/components/ImageViewer.vue'
beforeEach(()=>{
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
 vi.stubGlobal('ResizeObserver',class{observe(){} disconnect(){}})
})
afterEach(()=>vi.unstubAllGlobals())
it('switches images in place, resets zoom and closes on Escape without cancelling its parent',async()=>{
 const component=mount(ImageViewer,{props:{images:[{url:'/one.png',name:'第一张'},{url:'/two.png',name:'第二张'}],index:0},attachTo:document.body})
 await flushPromises()
 const wrapper=new DOMWrapper(document.body)
 expect(wrapper.get('dialog').attributes('open')).toBeDefined()
 const img=wrapper.get('img');Object.defineProperties(img.element,{naturalWidth:{value:1000},naturalHeight:{value:800}})
 await img.trigger('load');await wrapper.get('[aria-label="放大图片"]').trigger('click')
 expect(wrapper.get('[aria-label="缩放比例"]').text()).not.toBe('100%')
 await wrapper.get('[aria-label="下一张图片"]').trigger('click')
 expect(wrapper.get('img').attributes('src')).toBe('/two.png')
 expect(wrapper.get('[aria-label="缩放比例"]').text()).toBe('100%')
 await wrapper.get('dialog').trigger('keydown',{key:'ArrowLeft'})
 expect(wrapper.get('img').attributes('src')).toBe('/one.png')
 await wrapper.get('dialog').trigger('cancel')
 expect(component.emitted('close')).toHaveLength(1)
})
it('shows a recoverable image loading failure',async()=>{
 const wrapper=mount(ImageViewer,{props:{images:[{url:'/missing.png',name:'附件'}],index:0},global:{stubs:{Teleport:true}}})
 await wrapper.get('img').trigger('error')
 expect(wrapper.get('[role="alert"]').text()).toContain('未能加载')
 await wrapper.get('[aria-label="重新加载图片"]').trigger('click')
 expect(wrapper.find('[role="alert"]').exists()).toBe(false)
 expect(wrapper.get('[role="status"]').text()).toContain('加载')
})
