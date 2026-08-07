/* Service worker: what actually makes "works with the wifi off" true on an iPad.

   Without this the app is only offline in the sense that it makes no third-party
   requests. It would still need whatever machine is serving it to be switched on,
   which defeats the point of a thing bolted to a wall.

   Two tiers, because the split matters:

     SHELL is small (a few MB) and is fetched at install. After one visit the wall,
     every story, and every photo work with no network at all.

     The eight clips are ~86MB and are NOT precached. Downloading that on first paint
     would stall the install and, if it failed, would fail the whole registration.
     They are cached as they are played instead, and the settings panel has a button
     that pulls the lot down deliberately with a progress readout.

   iOS only runs service workers over HTTPS or on localhost. Served from a PC over
   plain http on the LAN this never registers, and the app still works exactly as
   before, just not offline. index.html handles that case rather than assuming.
*/

/* Bump this on every deploy. It is the only thing that evicts an old cache.
   BUILD is stamped by src/stamp-build.py so nobody has to remember. */
const VERSION = 'wall-v2';
const BUILD = '41aa773';
const SHELL_CACHE = VERSION + '-shell';
const MEDIA_CACHE = VERSION + '-media';

const SHELL = [
  './',
  './index.html',
  './art/books/01-hole-new-world.jpg',
  './art/books/02-enter-the-mine.jpg',
  './art/books/03-zombies-day-off.jpg',
  './art/books/04-into-the-overworld.jpg',
  './art/books/05-end-of-all-things.jpg',
  './art/books/06-activity-book.jpg',
  './art/slab.png',
  './art/icon.png',
  './art/cards.jpg',
  './art/carter.jpg',
  './art/jen.jpg',
  './art/luton.jpg',
  './art/qr/carter-freepcs.svg',
  './art/qr/carter-meeting.svg',
  './art/qr/jack-dad.svg',
  './art/qr/jack-dog.svg',
  './art/qr/jack-finale.svg',
  './art/qr/jack-grandma.svg',
  './art/qr/jack-label.svg',
  './art/qr/jack-mum.svg',
  './art/qr/jack-playbutton.svg',
  './art/qr/jack-sister.svg',
  './art/qr/jack-spoon.svg',
  './art/qr/jack-uncle.svg',
  './art/qr/jack-update.svg',
  './art/qr/shrek-awkward.svg',
  './art/qr/spoon-buying.svg',
  './art/shelf.jpg',
  './art/shrek.jpg',
  './art/wall-texture.png',
  './slab/photos/card-front.jpg',
  './slab/photos/card-inscription.jpg',
  './slab/photos/playbutton.jpg',
  './slab/photos/psa-1.jpg',
  './slab/photos/psa-2.jpg',
  './slab/photos/psa-3.jpg',
  './slab/photos/psa-4.jpg',
  './slab/photos/slab-label.png',
  './slab/photos/spoon-1.jpg',
  './slab/photos/spoon-2.jpg',
  './slab/photos/spoon-3.jpg',
  './slab/photos/spoon-4.jpg'
];

const CLIPS = [
  './slab/media/01-grandma.mp4',
  './slab/media/02-dad.mp4',
  './slab/media/03-mom.mp4',
  './slab/media/04-sister.mp4',
  './slab/media/05-dog.mp4',
  './slab/media/06-uncle.mp4',
  './slab/media/07-finale.mp4',
  './slab/media/08-update.mp4'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    /* Added one at a time rather than cache.addAll(). addAll is all-or-nothing, so a
       single artifact that has not been photographed yet would 404 and throw away the
       entire install, and the app would silently never go offline because of one missing
       jpg. Each miss is tolerated instead. */
    await Promise.all(SHELL.map(url =>
      cache.add(new Request(url, {cache: 'reload'})).catch(() => {})
    ));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(k => k !== SHELL_CACHE && k !== MEDIA_CACHE)
      .map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

const isClip = url => /\/slab\/media\/.+\.mp4$/.test(url.pathname);

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (isClip(url)) {
    /* Video is requested with a Range header. A cached 200 satisfies a range request
       in WebKit, but only if the whole response is stored, so partial (206) responses
       are deliberately never written to the cache, or seeking would break offline. */
    event.respondWith((async () => {
      const cache = await caches.open(MEDIA_CACHE);
      const hit = await cache.match(url.pathname, {ignoreSearch: true});
      if (hit) return hit;
      try {
        const fresh = await fetch(new Request(url.pathname, {cache: 'reload'}));
        if (fresh.ok && fresh.status === 200) {
          cache.put(url.pathname, fresh.clone());
        }
        return fresh;
      } catch (e) {
        return new Response('', {status: 504, statusText: 'offline, clip not saved yet'});
      }
    })());
    return;
  }

  /* The page itself is network-first, and this is the whole reason the app could not be
     updated. Everything was cache-first against a VERSION string that never changed, so
     once a device had installed the worker it served that index.html for ever: no deploy
     could reach it, and the wall stayed on whatever build it first saw. A wall-mounted
     iPad is exactly the device nobody thinks to clear the cache on.

     Network-first with a short timeout keeps the offline promise intact. If the network
     answers, that answer is fresh and gets stored. If it does not, the cache serves and
     the app opens anyway. */
  const isPage = req.mode === 'navigate' ||
                 url.pathname.endsWith('/') ||
                 url.pathname.endsWith('/index.html');

  if (isPage) {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(new Request(req.url, {cache: 'reload'}));
        if (fresh.ok) (await caches.open(SHELL_CACHE)).put('./index.html', fresh.clone());
        return fresh;
      } catch (e) {
        const hit = await caches.match('./index.html');
        if (hit) return hit;
        throw e;
      }
    })());
    return;
  }

  /* Everything else: serve from cache so it is instant and works offline, but always
     re-fetch in the background so the next load has the new one. Pure cache-first meant
     a corrected photograph never replaced the one already stored. */
  event.respondWith((async () => {
    const cache = await caches.open(SHELL_CACHE);
    const hit = await cache.match(req, {ignoreSearch: true});
    const network = fetch(req).then(fresh => {
      if (fresh.ok) cache.put(req, fresh.clone());
      return fresh;
    }).catch(() => null);
    return hit || (await network) || Response.error();
  })());
});

/* Deliberate bulk download, driven from the settings panel. Reports progress back so
   the panel can show which clip it is on rather than sitting there looking hung for
   the couple of minutes 86MB takes. */
self.addEventListener('message', event => {
  if (!event.data || event.data.type !== 'cache-clips') return;

  event.waitUntil((async () => {
    const cache = await caches.open(MEDIA_CACHE);
    const post = msg => self.clients.matchAll().then(cs => cs.forEach(c => c.postMessage(msg)));

    let done = 0;
    for (const url of CLIPS) {
      const already = await cache.match(url, {ignoreSearch: true});
      if (!already) {
        try {
          const res = await fetch(new Request(url, {cache: 'reload'}));
          if (res.ok && res.status === 200) await cache.put(url, res.clone());
        } catch (e) { /* report progress anyway; a retry can pick it up */ }
      }
      done++;
      await post({type: 'cache-progress', done, total: CLIPS.length});
    }

    const stored = (await cache.keys()).length;
    await post({type: 'cache-done', stored, total: CLIPS.length});
  })());
});
