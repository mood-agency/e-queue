addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url);
  const session_id = url.searchParams.get("session_id"); // Assuming session_id is passed as a URL query parameter

  // Fetch queue status from your Flask API
  const apiUrl = `https://yourdomain.com/api/queue_status/${session_id}`;
  const response = await fetch(apiUrl);
  const data = await response.json();

  if (data.in_queue && data.position > 0) {
    // User is in the queue, serve the splash screen
    return new Response(`<h1>You are in position ${data.position} in the queue.</h1>`, {
      headers: { 'content-type': 'text/html' },
    });
  } else {
    // Not in queue, fetch the original site content
    const siteResponse = await fetch('https://youractualsite.com');
    return siteResponse;
  }
}
