import { api } from '../../api/client'
import type { StockRow } from '../../types'
import { csvRows } from './chart'

export function downloadFile(url:string,filename:string){
  const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;anchor.click()
}

export async function exportTable(messageId:string,datasetRef:string){
  const data=await api<{table:StockRow[]}>(`/api/v1/stock/messages/${messageId}/artifacts/${datasetRef}?view=table`)
  const url=URL.createObjectURL(new Blob([csvRows(data.table)],{type:'text/csv;charset=utf-8'}))
  downloadFile(url,`${datasetRef}.csv`)
  setTimeout(()=>URL.revokeObjectURL(url),1000)
}
