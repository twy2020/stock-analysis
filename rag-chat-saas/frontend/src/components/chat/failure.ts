export function failureMessage(code?:string):string {
  const labels:Record<string,string>={
    INVALID_STOCK_ANSWER:'模型未返回有效的最终答复，本轮未完成。',
    STOCK_EVIDENCE_REQUIRED:'模型未取得本轮指标计算证据，回答已拦截。',
    STOCK_QUERY_FAILURE_LIMIT:'数据查询连续失败，已停止重试。',
    EMPTY_RESPONSE:'模型返回了空回复。',
    INVALID_PROVIDER_ENDPOINT:'模型接口地址返回了网页，请管理员检查 Base URL（通常包含 /v1）。',
    INVALID_RESPONSE_FORMAT:'模型接口未返回兼容的流式响应，请管理员检查接口协议。',
    UPSTREAM_STREAM_ERROR:'模型供应商在响应过程中返回错误，请稍后重试。',
    CONNECT_TIMEOUT:'连接模型接口超时，请稍后重试或联系管理员检查网络。',
    TIMEOUT:'等待模型响应超时，请稍后重试。',
    CONNECTION:'无法连接模型接口，请联系管理员检查网络和接口地址。',
    AUTHENTICATION:'模型接口认证失败，请管理员检查 API Key 和访问权限。',
    CREDENTIAL_UNAVAILABLE:'模型 API Key 尚未配置或无法读取，请联系管理员。',
    RATE_LIMIT:'模型接口限流或额度不足，请稍后重试或联系管理员。',
    INCOMPLETE_RESPONSE:'模型连接提前结束，答复尚未完成，可以重新回答。',
    CORE_STREAM_INTERRUPTED:'回复连接中断，可以重新回答。',
    CORE_UNAVAILABLE:'分析服务暂时无法连接，请稍后重试。',
    MODEL_UNAVAILABLE:'当前模型已停用或不可用，请管理员检查模型设置。',
    MODEL_FORBIDDEN:'当前应用没有该模型的使用权限，请管理员检查授权。',
    UPSTREAM:'模型供应商接口异常，请稍后重试或联系管理员。',
    OUTPUT_LIMIT:'模型生成内容超出本轮上限，尚未完成。请缩小问题范围或重新回答。',
    CANCELLED:'已停止回复',
  }
  return labels[code??'']??'本轮未完成，可以重新回答或继续提问'
}
