import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
markdown.disable('image')
markdown.inline.ruler.before('link','data-reference',(state,silent)=>{
  const match=state.src.slice(state.pos).match(/^\[data:(ds_[a-f0-9]{32})\]/)
  const refs=state.env.dataReferences as Record<string,string>|undefined
  if(!match||!refs?.[match[1]])return false
  if(!silent){const token=state.push('html_inline','',0);token.content=`<button type="button" class="inline-data-reference" data-dataset-ref="${match[1]}" title="${markdown.utils.escapeHtml(refs[match[1]])}">数据</button>`}
  state.pos+=match[0].length;return true
})
markdown.inline.ruler.before('link', 'source-citation', (state, silent) => {
  if (state.src[state.pos] !== '[') return false
  const match = state.src.slice(state.pos).match(/^\[(?:来源\s*|Evidence\s*)?(\d+)\]/)
  if (!match || state.src[state.pos + match[0].length] === '(' || !(state.env.citationNumbers as Set<number> | undefined)?.has(Number(match[1]))) return false
  if (!silent) {
    const token = state.push('html_inline', '', 0)
    const label = (state.env.citationLabels as Record<number, string> | undefined)?.[Number(match[1])] ?? `查看来源 ${match[1]}`
    token.content = `<button type="button" class="inline-citation" data-citation-rank="${match[1]}" aria-label="${markdown.utils.escapeHtml(label)}">${match[1]}</button>`
  }
  state.pos += match[0].length
  return true
})

const defaultLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLink ? defaultLink(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options)
}

export function renderMarkdown(value: string, citationNumbers: number[] = [], citationLabels: Record<number, string> = {}, dataReferences: Record<string,string> = {}): string {
  const marker='历史数据集引用（数值需用stock_dataset在本轮复核）：'
  const offset=value.indexOf(marker)
  if(offset>=0){
    try{
      const entries:unknown=JSON.parse(value.slice(offset+marker.length).trim())
      if(Array.isArray(entries)&&entries.length&&entries.every(item=>typeof item?.datasetRef==='string'&&dataReferences[item.datasetRef])){
        value=value.slice(0,offset)+'\n\n数据来源：'+entries.map(item=>`[data:${item.datasetRef}]`).join(' ')
      }
    }catch{/* Partial streamed JSON stays plain text until its structure is complete. */}
  }
  return DOMPurify.sanitize(markdown.render(value, { citationNumbers: new Set(citationNumbers), citationLabels, dataReferences }), {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target'],
    FORBID_TAGS: ['img', 'iframe', 'style'],
  })
}
