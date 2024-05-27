/**
 * Welcome to Cloudflare Workers! This is your first worker.
 *
 * - Run `wrangler dev src/index.ts` in your terminal to start a development server
 * - Open a browser tab at http://localhost:8787/ to see your worker in action
 * - Run `wrangler deploy src/index.ts --name my-worker` to deploy your worker
 *
 * Learn more at https://developers.cloudflare.com/workers/
 */

export interface Env {
    e_queue: KVNamespace;
}

export interface Env {
    SESSION_KV: KVNamespace;
}

export default {
    async fetch(request, env, ctx) {
        let url = new URL(request.url);
        // if url is none
        if (!url) {
            url = new URL('https://example.com');
        }
        let session_id = getSessionId(request);

        if (!session_id) {
            // Generate a new session ID if one isn't provided in the cookies
            session_id = generateSessionId();
            await env.SESSION_KV.put(`session:${session_id}`, JSON.stringify({timestamp: Date.now()}));
        }

        // Fetch queue status from your API if session is valid
        const apiUrl = `http://localhost:5000/api/queue_status/${session_id}`;
        // const apiUrl = `${env.API_URL}api/queue_status/${session_id}`;
        console.log(apiUrl)
        const response = await fetch(apiUrl);
        const data = await response.json();

        let headers = new Headers(response.headers);
        if (data.in_queue && data.position > 0) {
            // User is in the queue, serve the splash screen
            // Set a cookie with the session ID
            headers.append('Set-Cookie', `session_id=${session_id}; HttpOnly; Path=/; Max-Age=86400`);
            return new Response(`<h1>You are in position ${data.position} in the queue.</h1>`, {
                headers: headers,
                status: 200
            });
        } else {
            // Not in queue, fetch the original site content from the host of the incoming request
            const originalHostUrl = `https://${url}/`; // Assuming HTTPS is used
            const siteResponse = await fetch(originalHostUrl);
            headers.append('Set-Cookie', `session_id=${session_id}; HttpOnly; Path=/; Max-Age=86400`);
            return new Response(siteResponse.body, {
                status: siteResponse.status,
                headers: headers
            });
        }
    }
};

/**
 * Extract session ID from request cookies
 *
 * @param {Request} request
 * @returns {string | undefined}
 */
function getSessionId(request: { url?: string | URL; headers?: any; }) {
    const cookieString = request.headers.get('Cookie');
    const cookies = cookieString ? cookieString.split(';').reduce((acc: { [x: string]: any; }, cookie: string) => {
        const parts = cookie.split('=');
        acc[parts[0].trim()] = parts[1];
        return acc;
    }, {}) : {};
    return cookies['session_id'];
}

/**
 * Generate a unique session ID
 *
 * @returns {string}
 */
function generateSessionId() {
    return Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
}
