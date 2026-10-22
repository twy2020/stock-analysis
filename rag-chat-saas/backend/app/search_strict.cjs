// Aggregation owns failover: each subprocess must report only its selected engine.
const engines = require('/opt/stock-search/node_modules/ai-search-mcp/src/engines');
const proxyUrl = process.env.SEARCH_HTTP_PROXY;
if (proxyUrl) {
  const proxy = new URL(proxyUrl);
  if (proxy.protocol === 'socks5:') {
    const { socksDispatcher } = require('/opt/stock-socks/node_modules/fetch-socks');
    const http = require(require.resolve('undici', { paths: ['/opt/stock-socks/node_modules/fetch-socks'] }));
    const dispatcher = socksDispatcher({ type: 5, host: proxy.hostname, port: Number(proxy.port),
      ...(proxy.username ? { userId: decodeURIComponent(proxy.username), password: decodeURIComponent(proxy.password) } : {}) });
    http.setGlobalDispatcher(dispatcher);
    globalThis.fetch = (input, options) => http.fetch(input, { ...options, dispatcher });
    // The package bootstrap only understands HTTP proxies. Keep our SOCKS
    // dispatcher rather than letting it construct an HTTP ProxyAgent for it.
    require('/opt/stock-search/node_modules/ai-search-mcp/src/utils/http').applyProxy = () => {};
  } else {
    require('/opt/stock-search/node_modules/ai-search-mcp/src/utils/http').applyProxy(proxyUrl);
    globalThis.fetch = require(require.resolve('undici', { paths: ['/opt/stock-search/node_modules/ai-search-mcp'] })).fetch;
  }
}
const resolve = engines.resolveEngineNames;
engines.resolveEngineNames = (config, region, query) =>
  process.env.SEARCH_STRICT_ENGINE === '1' ? [config.engine] : resolve(config, region, query);
