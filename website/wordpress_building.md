# Building with WordPress

Most pages of molonari.io are no longer edited in WordPress. They live in git, in this repository, and are pushed to the site by `molosite`. Only the editorial pages are edited in the WordPress editor.

## Who edits what

| Mode | Pages today | Edited | How it reaches the site |
|---|---|---|---|
| `generated` | `development`, `operating-space`, `get-started` | the template `website/templates/<slug>.md.j2` (Markdown with Jinja), or the sources it reads in the `CGS-MOLO` branch of the Operating Space | `pixi run site push` |
| `managed` | `molonari` (front), `molonari-1d`, `lab-testing` | the raw block file `website/pages/<slug>.html` | `pixi run site push` |
| `editorial` | `gallery`, `results`, `askdb` | in WordPress, in the editor | nothing: `molosite` never touches them |

The page map, with each page's id and mode, is `website/site.toml`. A page absent from it is never touched either.

## The routine (from the Operating Space, in a terminal)

```bash
export MOLO_WP_USER=molosite
read -rs MOLO_WP_APP_PASSWORD && export MOLO_WP_APP_PASSWORD   # the application password of the molosite account

pixi run molo update .config/molonari.cgs   # the sources must not be behind CGS-MOLO
pixi run site plan                          # unchanged | update (with the diff) | create | drift; writes nothing
git add -A && git commit -m "..."           # push refuses a dirty checkout
pixi run site push                          # applies the plan
```

Each pushed page ends with a hidden marker (the source commit and the hash of the content). If somebody edits a generated or managed page in WordPress, the next `plan` says `drift` and `push` refuses that page. Take the edit into git with `pixi run site pull <slug>`, review it, commit it, then `pixi run site push --adopt <slug>`. Before every update the live page is saved to `.dev/.backup/<date>/`, and WordPress revisions are a second copy.

The credentials are read from the two environment variables only. Never write them in a file of the tree. The account has the Editor role, never Administrator, and its application password can be revoked on its own (Users, `molosite`, Application Passwords).

## What cannot be pushed

The menu, the header and the footer belong to the Site editor. They are set by hand in WordPress (`Appearance > Editor > Navigation`). `molosite` writes page content and media only, never a plugin, a theme or PHP.

## The server side the sync needs

Three things on the VPS are not in git. The first two are needed for the REST login to work, the third for the certificate renewal:
- in the nginx site (`/etc/nginx/sites-available/molonari.io`), in the `location ~ \.php$` block: `fastcgi_param HTTP_AUTHORIZATION $http_authorization;`
- the must-use plugin `wp-content/mu-plugins/molosite-basic-auth.php`, which copies the Basic login of the `Authorization` header into `PHP_AUTH_USER` and `PHP_AUTH_PW`.

- in the same nginx file, `www.molonari.io` is in both `server_name` lines and the port-80 redirect is `if ($host ~ ^(www\.)?molonari\.io$) { return 301 https://$host$request_uri; }`. Without it the Let's Encrypt challenge for `www` gets a 404 and `certbot renew --dry-run` fails (INCIDENT_20261111, the "www" failure).

Rebuilding the VPS means redoing all three. Without them, `pixi run site` fails with `rest_not_logged_in`.

## The server routine

The VPS runs `molosite` by itself, so a commit on `CGS-MOLO` reaches the site within the hour. Everything below is on the VPS, as root, and none of it is in git:

| What | Where |
|---|---|
| Operating Space (the public repositories, from `.config/molonari-vps.cgs`) | `/root/.cgs/MOLONARI-vps-<date>`; the gate is its `molonari.io/` |
| Credentials: an application password named `molosite-vps` of the `molosite` account | `/root/.molosite.env`, mode `600`, exports `MOLO_WP_USER` and `MOLO_WP_APP_PASSWORD` |
| The settings: the space, its `.cgs`, the receiver and its database | `/etc/molonari/vps.env`, from `server/vps/vps.env.example` |
| The script | `/usr/local/sbin/molosite-sync`, from `server/vps/molosite-sync.sh`: `molo update`, then `pixi run --frozen site push`, under `flock` |
| The schedule | root crontab: `17 * * * * /usr/local/sbin/molosite-sync >> /var/log/molosite-sync.log 2>&1` |
| The log, rotated weekly | `/var/log/molosite-sync.log`, rotation in `/etc/logrotate.d/molosite-sync` |

Read the last run with `tail -30 /var/log/molosite-sync.log`. A run ending in `exit 1` needs a person, almost always a page in `drift`: nothing was overwritten. Run it by hand with `/usr/local/sbin/molosite-sync`.

`--frozen` matters: without it pixi rewrites the gate's `pixi.lock` each time the gate version moves, the checkout becomes dirty and `push` refuses. Never run `pixi lock` in that checkout. To stop the sync, remove the cron line, or revoke the `molosite-vps` application password in WordPress (it gives no administrator rights).

The full record of the server setup, and how to rebuild it, is [server/OperatingSpaceDeploy.md](../server/OperatingSpaceDeploy.md). Changing the `.cgs`, the receiver or its database is [server/reset-data-receiver.md](../server/reset-data-receiver.md).

## Editing an editorial page in WordPress

WordPress is a tool that helps us build robust HTML/CSS pages quickly.

There are 2 main components for a WordPress page:
- the 'Page' itself
- the 'Site': content that surrounds the page (header, footer, overall appearance, etc.)

### Logging in as admin

The `/wp-admin` URL is by default blocked for admin connection. Once logged, you should see a black panel on top of the website pages. From there, you can navigate to the Dashboard, edit the site (overall appearance), add a new page or edit the current page.

### Building a page

The page/site editor is intuitive if you know the basics of web architecture. It allows you to add/move/delete blocks like
- text
- header
- image
- gallery (many images)
- groups (`div` to combine other components)

When one element is focused, you can change its style on the right panel, or select the parent element by clicking the left-most button that appears on top of the element.

You can then click publish or save in order to save your changes. The effect is immediate on the website.

### Plugins

WordPress allows for plugins that are very useful for a quick deployment of the website. The ones used by the MOLONARI project are:
- `MathJax-LaTeX`, for equations rendering
- `Page scroll to id`, for a smooth scroll of the page

Those are accessible from `Dashboard > Plugins`.

We can also create custom packages for more precise operations. More details about that in `wordpress_sqlite_plugin.md`.