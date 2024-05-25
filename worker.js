addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  let url = new URL(request.url);
  let session_id = getSessionId(request);

  if (!session_id) {
    // Generate a new session ID if one isn't provided in the cookies
    session_id = generateSessionId();
    await SESSION_KV.put(`session:${session_id}`, JSON.stringify({timestamp: Date.now()}));
  }

  // Fetch queue status from your API if session is valid
  const apiUrl = `https://yourdomain.com/api/queue_status/${session_id}`;
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
    // Not in queue, fetch the original site content
    const siteResponse = await fetch('https://youractualsite.com');
    headers.append('Set-Cookie', `session_id=${session_id}; HttpOnly; Path=/; Max-Age=86400`);
    return new Response(siteResponse.body, {
      status: siteResponse.status,
      headers: headers
    });
  }
}

function getSessionId(request) {
  const cookieString = request.headers.get('Cookie');
  const cookies = cookieString ? cookieString.split(';').reduce((acc, cookie) => {
    const parts = cookie.split('=');
    acc[parts[0].trim()] = parts[1];
    return acc;
  }, {}) : {};
  return cookies['session_id'];
}

function generateSessionId() {
  // Simple unique session ID generator
  return Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
}
