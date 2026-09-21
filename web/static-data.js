// Static-host adapter. Loaded only by the generated hosted site.
window.ATLAS_STATIC = true;
const historyCache = new Map();
window.atlasApi = async function(url) {
    const route = new URL(url, 'http://local');
    if (route.pathname === '/api/symbols') {
        const response = await fetch('./symbols.json', {cache:'no-cache'});
        if (!response.ok) throw Error('The asset catalog is unavailable. Please try refreshing.');
        historyCache.clear();
        return response.json();
    }
    const symbol = route.searchParams.get('symbol');
    const start = route.searchParams.get('start') || '0001-01-01';
    const end = route.searchParams.get('end') || '9999-12-31';
    if (start > end) throw Error('Start date must be before the end date.');
    if (!historyCache.has(symbol)) {
        const response = await fetch('./prices/' + encodeURIComponent(symbol) + '.json.gz');
        if (!response.ok) throw Error('Price history is unavailable for this asset.');
        const stream = response.body.pipeThrough(new DecompressionStream('gzip'));
        const data = await new Response(stream).json();
        const records = data.rows.map(row=>Object.fromEntries(data.columns.map((key,i)=>[key,row[i]])));
        // Limit browser memory while moving through a large universe.
        if (historyCache.size >= 5) historyCache.delete(historyCache.keys().next().value);
        historyCache.set(symbol, records);
    }
    return historyCache.get(symbol).filter(row=>row.date>=start && row.date<=end);
};
