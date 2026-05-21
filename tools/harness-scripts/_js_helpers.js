// Shared JS helpers injected into harness scripts as $js_helpers by
// harness_utils.load_script. Keep this file ASCII and dependency-free.

function clean(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
}

function seekReduxDataFromHtml() {
    const marker = 'window.SEEK_REDUX_DATA = ';
    const html = document.documentElement?.outerHTML || '';
    const markerIndex = html.indexOf(marker);
    if (markerIndex < 0) return null;

    const start = markerIndex + marker.length;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < html.length; i++) {
        const ch = html[i];
        if (inString) {
            if (escaped) {
                escaped = false;
            } else if (ch === '\\') {
                escaped = true;
            } else if (ch === '"') {
                inString = false;
            }
            continue;
        }
        if (ch === '"') {
            inString = true;
        } else if (ch === '{') {
            depth += 1;
        } else if (ch === '}') {
            depth -= 1;
            if (depth === 0) {
                try {
                    return JSON.parse(html.slice(start, i + 1));
                } catch (_) {
                    return null;
                }
            }
        }
    }
    return null;
}
