#!/usr/bin/env bash
# recov-https-certificate.sh
#
# Automates RECOVERY_HTTPS_CERTIFICATE.md (steps 1 to 7 + backup) and writes
# an incident report INCIDENT_<TimeStamp>.md in the same format as the former ones.
#
# Run as root on the VPS:   sudo ./recov-https-certificate.sh
#
# Environment overrides:
#   DOMAINS="molonari.io www.molonari.io"   first one = certificate name
#   WEBROOT=/var/www/html/molonari.io/wordpress
#   VHOST=/etc/nginx/sites-available/molonari.io
#   BACKUP_DIR=/root/backups
#   REPORT_DIR=<directory of this script>
#   CERTBOT_EMAIL=you@example.org           (otherwise registers without email
#                                            if no ACME account exists yet)
#   FORCE=1                                 recreate the certificate even if a
#                                            valid one is already present
#
# Safety: everything touched is backed up first; if anything fails after the
# nginx vhost has been modified, the original vhost is restored and nginx
# is restarted. The report is written in all cases.

set -uo pipefail

DOMAINS="${DOMAINS:-molonari.io www.molonari.io}"
WEBROOT="${WEBROOT:-/var/www/html/molonari.io/wordpress}"
VHOST="${VHOST:-/etc/nginx/sites-available/molonari.io}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${REPORT_DIR:-$SCRIPT_DIR}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
FORCE="${FORCE:-0}"

read -r -a DOMAIN_ARR <<<"$DOMAINS"
CERT_NAME="${DOMAIN_ARR[0]}"
LIVE_DIR="/etc/letsencrypt/live/$CERT_NAME"
TS="$(date +%Y%m%d_%H%M%S)"
DAY="$(date +%Y%m%d)"
NOW_HUMAN="$(date '+%d %B %Y %H:%M:%S %Z')"
REPORT="$REPORT_DIR/INCIDENT_${DAY}.md"
[ -e "$REPORT" ] && REPORT="$REPORT_DIR/INCIDENT_${TS}.md"
WORK="$(mktemp -d)"
LOGFILE="$WORK/run.log"

STATUS="en cours"
FAILED_STEP=""
VHOST_MODIFIED=0
BACKUP_FILE=""
VHOST_BACKUP=""
CERT_ACTION="aucune"
HTTPS_CODE=""
DRYRUN_OK=""

# ---------------------------------------------------------------- helpers
say()  { printf '\n\033[1m== %s\033[0m\n' "$*" | tee -a "$LOGFILE"; }
info() { printf '%s\n' "$*" | tee -a "$LOGFILE"; }
# run a command, show + log its output, return its exit status
run()  { { printf '$ %s\n' "$*"; "$@" 2>&1; } | tee -a "$LOGFILE"; return "${PIPESTATUS[0]}"; }
# run a command and capture its output (for the report) in file $1
cap()  { local f="$1"; shift; { printf '$ %s\n' "$*"; "$@" 2>&1; } >"$f"; return 0; }

fail() {
  FAILED_STEP="$1"
  STATUS="échec à l'étape : $1"
  info "ERREUR : $1"
  exit 1
}

nginx_cert_missing() {
  # print every ssl_certificate path referenced by enabled sites that does not exist
  grep -rhE '^\s*ssl_certificate(_key)?\s' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null \
    | sed -E 's/^\s*ssl_certificate(_key)?\s+//; s/;.*$//' | sort -u \
    | while read -r p; do [ -e "$p" ] || echo "$p"; done
}

# ---------------------------------------------------------------- report
write_report() {
  {
    echo "# MOLONARI.io — Note d’incident"
    echo
    echo "**Date :** $NOW_HUMAN"
    echo "**VPS :** \`$(hostname -f 2>/dev/null || hostname)\`"
    echo "**Service affecté :** \`https://$CERT_NAME\`"
    echo "**Statut :** $STATUS"
    echo "**Nature :** disparition / invalidité du certificat Let's Encrypt (rapport généré par \`recov-https-certificate.sh\`)"
    echo
    echo "## 1. Symptôme"
    echo
    echo "État initial des services :"
    echo
    echo '```text'
    cat "$WORK/services_before.txt" 2>/dev/null
    echo '```'
    echo
    echo "Test de configuration nginx avant intervention :"
    echo
    echo '```text'
    cat "$WORK/nginx_t_before.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 2. Diagnostic Let's Encrypt"
    echo
    echo '```text'
    cat "$WORK/le_before.txt" 2>/dev/null
    echo '```'
    echo
    echo "Chemins SSL référencés par nginx mais absents :"
    echo
    echo '```text'
    cat "$WORK/missing_before.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 3. Configuration nginx"
    echo
    echo '```text'
    cat "$WORK/vhost_info.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 4. Certbot automatique / journaux"
    echo
    echo '```text'
    cat "$WORK/certbot_journal.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 5. Éléments d’investigation (cause racine)"
    echo
    echo '```text'
    cat "$WORK/forensics.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 6. Sauvegarde et restauration"
    echo
    echo "* Sauvegarde : \`${BACKUP_FILE:-non effectuée}\`"
    echo "* Copie du vhost original : \`${VHOST_BACKUP:-non effectuée}\`"
    echo "* Action sur le certificat : **$CERT_ACTION**"
    echo "* Vhost nginx modifié temporairement : $([ "$VHOST_MODIFIED" = 1 ] && echo oui || echo non)"
    echo
    echo "## 7. Journal d’exécution"
    echo
    echo '```text'
    sed 's/\x1b\[[0-9;]*m//g' "$LOGFILE"
    echo '```'
    echo
    echo "## 8. Validation finale"
    echo
    echo '```text'
    cat "$WORK/final.txt" 2>/dev/null
    echo '```'
    echo
    echo "## 9. Actions différées"
    echo
    echo "1. diagnostiquer Dovecot / Postfix s’ils sont toujours en échec ;"
    echo "2. analyser les journaux Certbot et système autour de l’incident ;"
    echo "3. demander à HOST l’historique des interventions sur le VPS (maintenance, snapshot, restauration) ;"
    echo "4. mettre en place une surveillance indépendante de \`/etc/letsencrypt\` afin d’horodater toute suppression future ;"
    echo "5. réévaluer le maintien du VPS chez HOST si l’intégrité de l’état système ne peut pas être garantie."
    echo
    echo "## Conclusion"
    echo
    echo "**$STATUS**"
    echo
    echo "Cause racine : non déterminée par ce script (voir section 5)."
  } >"$REPORT" 2>/dev/null
  echo
  echo "Rapport écrit : $REPORT"
}

# ---------------------------------------------------------------- rollback / exit
on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ "$VHOST_MODIFIED" = 1 ] && [ -n "$VHOST_BACKUP" ]; then
    info "Rollback : restauration du vhost d'origine"
    cp -a "$VHOST_BACKUP" "$VHOST"
    if nginx -t >>"$LOGFILE" 2>&1; then
      systemctl restart nginx >>"$LOGFILE" 2>&1 || true
    else
      info "nginx -t échoue encore après rollback : repli sur la config HTTP temporaire non possible, intervention manuelle requise"
    fi
  fi
  [ "$rc" -ne 0 ] && [ "$STATUS" = "en cours" ] && STATUS="échec (code $rc)"
  { printf '$ systemctl is-active nginx\n'; systemctl is-active nginx 2>&1; } >"$WORK/final.txt" || true
  write_report
  rm -rf "$WORK"
  exit "$rc"
}
trap on_exit EXIT

# ---------------------------------------------------------------- preflight
[ "$(id -u)" -eq 0 ] || { echo "À lancer en root (sudo)." >&2; STATUS="non exécuté (pas root)"; exit 1; }
for c in nginx certbot curl tar systemctl; do
  command -v "$c" >/dev/null || { echo "Commande manquante : $c" >&2; STATUS="non exécuté ($c manquant)"; exit 1; }
done
[ -f "$VHOST" ] || { echo "Vhost introuvable : $VHOST" >&2; STATUS="non exécuté (vhost introuvable)"; exit 1; }
[ -d "$WEBROOT" ] || { echo "Webroot introuvable : $WEBROOT" >&2; STATUS="non exécuté (webroot introuvable)"; exit 1; }
mkdir -p "$BACKUP_DIR" "$REPORT_DIR"

# ---------------------------------------------------------------- step 1 : diagnostic
say "Étape 1 - Diagnostic (état initial)"
cap "$WORK/services_before.txt" systemctl --no-pager --failed
{ echo; systemctl is-active nginx dovecot postfix 2>&1 | paste -d' ' <(printf 'nginx\ndovecot\npostfix\n') -; } >>"$WORK/services_before.txt"
cap "$WORK/nginx_t_before.txt" nginx -t
nginx_cert_missing >"$WORK/missing_before.txt"
{
  echo '$ certbot certificates'; certbot certificates 2>&1
  echo; echo '$ ls -l /etc/letsencrypt/live/';    ls -l /etc/letsencrypt/live/ 2>&1
  echo; echo '$ ls -l /etc/letsencrypt/archive/'; ls -l /etc/letsencrypt/archive/ 2>&1
  echo; echo '$ ls -l /etc/letsencrypt/renewal/'; ls -l /etc/letsencrypt/renewal/ 2>&1
} >"$WORK/le_before.txt"
{
  echo '$ ls -l --time-style=full-iso' "$VHOST" /etc/nginx/sites-enabled/
  ls -l --time-style=full-iso "$VHOST" /etc/nginx/sites-enabled/ 2>&1
  echo; echo '$ grep -R ssl_certificate /etc/nginx/sites-enabled/'
  grep -R "ssl_certificate" /etc/nginx/sites-enabled/ 2>&1
} >"$WORK/vhost_info.txt"
{
  echo '$ systemctl list-timers certbot*'; systemctl list-timers 'certbot*' --no-pager 2>&1
  echo; echo '$ journalctl -u certbot --since "60 days ago"'; journalctl -u certbot --since "60 days ago" --no-pager 2>&1 | tail -n 40
} >"$WORK/certbot_journal.txt"
{
  echo '$ uptime -s'; uptime -s
  echo; echo '$ last -n 15 -F'; last -n 15 -F 2>&1
  echo; echo '$ lastlog -b 0 (derniers accès)'; lastlog -b 0 2>&1 | head -n 20
  echo; echo '$ ls -ld --time-style=full-iso /etc/letsencrypt /etc/letsencrypt/*'
  ls -ld --time-style=full-iso /etc/letsencrypt /etc/letsencrypt/* 2>&1
  echo; echo '$ crontab -l'; crontab -l 2>&1
  echo; echo '$ grep letsencrypt (journal 60j)'
  journalctl --since "60 days ago" --no-pager 2>/dev/null | grep -i letsencrypt | tail -n 20
  echo; echo '$ grep -ri letsencrypt /usr/local/ispconfig/server/scripts (appels ISPConfig)'
  grep -rIl "letsencrypt" /usr/local/ispconfig/server/ 2>/dev/null | head -n 10
} >"$WORK/forensics.txt"
info "Diagnostic collecté."

# ---------------------------------------------------------------- backup
say "Sauvegarde de /etc/nginx et /etc/letsencrypt"
BACKUP_FILE="$BACKUP_DIR/molonari_https_backup_${TS}.tar.gz"
if tar czf "$BACKUP_FILE" /etc/nginx /etc/letsencrypt 2>>"$LOGFILE"; then
  chmod 600 "$BACKUP_FILE"
  tar tzf "$BACKUP_FILE" >/dev/null 2>&1 || fail "sauvegarde illisible : $BACKUP_FILE"
  info "Sauvegarde OK : $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
  fail "sauvegarde tar"
fi
VHOST_BACKUP="$BACKUP_DIR/$(basename "$VHOST").${TS}.orig"
cp -a "$VHOST" "$VHOST_BACKUP" || fail "copie du vhost"
info "Copie du vhost : $VHOST_BACKUP"

# ---------------------------------------------------------------- decide
cert_ok=0
if [ -s "$LIVE_DIR/fullchain.pem" ] && [ -s "$LIVE_DIR/privkey.pem" ] \
   && openssl x509 -in "$LIVE_DIR/fullchain.pem" -noout -checkend 604800 >/dev/null 2>&1; then
  cert_ok=1
fi
if [ "$cert_ok" = 1 ] && [ "$FORCE" != 1 ]; then
  say "Certificat valide présent (> 7 jours) : pas de recréation (FORCE=1 pour forcer)"
  CERT_ACTION="conservé (déjà valide)"
  if nginx -t >>"$LOGFILE" 2>&1; then
    systemctl is-active --quiet nginx || run systemctl restart nginx
    STATUS="rien à réparer : certificat valide, nginx OK"
    { run curl -Ik --max-time 20 "https://$CERT_NAME"; } >"$WORK/final.txt" 2>&1
    exit 0
  fi
  info "Certificat valide mais nginx -t échoue : poursuite de la procédure"
fi

# ---------------------------------------------------------------- step 2 : HTTP only
say "Étape 2 - Désactivation temporaire du HTTPS (vhost HTTP seul)"
PHP_SOCK="$(ls /var/run/php/php*-fpm.sock 2>/dev/null | head -n1)"
[ -n "$PHP_SOCK" ] || info "Avertissement : aucun socket PHP-FPM trouvé, le bloc PHP est omis"

# other enabled files referencing missing certificates would still block nginx
EXTRA_STASH=()
while IFS= read -r f; do
  [ "$(readlink -f "$f")" = "$(readlink -f "$VHOST")" ] && continue
  if nginx_cert_missing_in=$(grep -hE '^\s*ssl_certificate\s' "$f" | sed -E 's/^\s*ssl_certificate\s+//; s/;.*$//' | while read -r p; do [ -e "$p" ] || echo "$p"; done) \
     && [ -n "$nginx_cert_missing_in" ]; then
    EXTRA_STASH+=("$f")
  fi
done < <(find /etc/nginx/sites-enabled /etc/nginx/conf.d -maxdepth 1 \( -type f -o -type l \) 2>/dev/null)

STASH_DIR="$WORK/stash"; mkdir -p "$STASH_DIR"
for f in "${EXTRA_STASH[@]}"; do
  info "Désactivation temporaire (certificat absent) : $f"
  mv "$f" "$STASH_DIR/$(echo "$f" | tr / _)" || fail "désactivation de $f"
  echo "$f" >>"$STASH_DIR/index"
done
restore_stash() {
  [ -f "$STASH_DIR/index" ] || return 0
  while IFS= read -r f; do mv "$STASH_DIR/$(echo "$f" | tr / _)" "$f"; done <"$STASH_DIR/index"
  rm -f "$STASH_DIR/index"
}
# restore stashed files too if we exit abnormally
trap 'rc=$?; [ $rc -ne 0 ] && restore_stash; on_exit' EXIT

{
  echo "server {"
  echo "    listen 80;"
  echo "    listen [::]:80;"
  echo
  echo "    server_name $DOMAINS;"
  echo
  echo "    root $WEBROOT;"
  echo "    index index.php index.html index.htm;"
  echo
  echo "    location / {"
  echo '        try_files $uri $uri/ /index.php?$args;'
  echo "    }"
  if [ -n "$PHP_SOCK" ]; then
    echo
    echo '    location ~ \.php$ {'
    echo "        include snippets/fastcgi-php.conf;"
    echo "        fastcgi_pass unix:$PHP_SOCK;"
    echo "    }"
  fi
  echo "}"
} >"$WORK/http-only.conf"

VHOST_MODIFIED=1
cp "$WORK/http-only.conf" "$VHOST" || fail "écriture du vhost HTTP"
[ -e "/etc/nginx/sites-enabled/$(basename "$VHOST")" ] || ln -s "$VHOST" "/etc/nginx/sites-enabled/$(basename "$VHOST")"

say "Étape 3 - Test et redémarrage nginx"
run nginx -t || fail "nginx -t avec vhost HTTP seul"
run systemctl restart nginx || fail "redémarrage nginx (HTTP seul)"
run curl -sI --max-time 20 http://localhost || fail "curl http://localhost"

# ---------------------------------------------------------------- step 4 : certbot
say "Étape 4 - Création du certificat"
CB=(certbot certonly --webroot -w "$WEBROOT" --cert-name "$CERT_NAME" --non-interactive --agree-tos)
for d in "${DOMAIN_ARR[@]}"; do CB+=(-d "$d"); done
if [ -n "$CERTBOT_EMAIL" ]; then CB+=(-m "$CERTBOT_EMAIL")
elif ! ls /etc/letsencrypt/accounts/*/*/* >/dev/null 2>&1; then CB+=(--register-unsafely-without-email); fi
[ "$FORCE" = 1 ] && CB+=(--force-renewal)
run "${CB[@]}" || fail "certbot certonly"
[ -s "$LIVE_DIR/fullchain.pem" ] && [ -s "$LIVE_DIR/privkey.pem" ] || fail "fichiers de certificat absents après certbot"
run ls -l "$LIVE_DIR/"
CERT_ACTION="recréé via certbot ($(date +%H:%M))"

# ---------------------------------------------------------------- step 5 : restore HTTPS
say "Étape 5 - Restauration de la configuration HTTPS d'origine"
cp -a "$VHOST_BACKUP" "$VHOST" || fail "restauration du vhost"
restore_stash
for f in /etc/letsencrypt/options-ssl-nginx.conf /etc/letsencrypt/ssl-dhparams.pem; do
  if grep -q "$f" "$VHOST" && [ ! -e "$f" ]; then
    info "Fichier manquant référencé par le vhost : $f (récupération depuis la sauvegarde ou certbot)"
    tar xzf "$BACKUP_FILE" -C / "${f#/}" 2>/dev/null || true
    [ -e "$f" ] || info "ATTENTION : $f toujours absent (voir étape 6)"
  fi
done

# ---------------------------------------------------------------- step 6 : reload
say "Étape 6 - Rechargement nginx"
run nginx -t || fail "nginx -t avec vhost HTTPS restauré"
VHOST_MODIFIED=0   # vhost is back to the original: no rollback needed anymore
run systemctl reload nginx || fail "reload nginx"

# ---------------------------------------------------------------- step 7 : validate
say "Étape 7 - Validation"
{
  echo '$ curl -Ik https://'"$CERT_NAME"
  curl -Ik --max-time 20 "https://$CERT_NAME" 2>&1
} >"$WORK/final.txt"
cat "$WORK/final.txt" | tee -a "$LOGFILE"
HTTPS_CODE="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 20 "https://$CERT_NAME" 2>/dev/null)"

{ echo; echo '$ certbot renew --dry-run'; certbot renew --dry-run 2>&1; } >"$WORK/dry.txt"
if grep -q "all simulated renewals succeeded" "$WORK/dry.txt"; then DRYRUN_OK="oui"; else DRYRUN_OK="non"; fi
tail -n 15 "$WORK/dry.txt" | tee -a "$LOGFILE"
cat "$WORK/dry.txt" >>"$WORK/final.txt"

say "Services associés (Dovecot / Postfix)"
for s in dovecot postfix; do
  if ! systemctl is-active --quiet "$s"; then
    info "$s inactif : tentative de redémarrage"
    systemctl restart "$s" >>"$LOGFILE" 2>&1 || true
  fi
  info "$s : $(systemctl is-active "$s" 2>&1)"
  echo "$s : $(systemctl is-active "$s" 2>&1)" >>"$WORK/final.txt"
done

case "$HTTPS_CODE" in
  2??|3??) if [ "$DRYRUN_OK" = "oui" ]; then
             STATUS="résolu : certificat recréé, HTTPS répond ($HTTPS_CODE), renouvellement simulé OK"
           else
             STATUS="partiellement résolu : HTTPS répond ($HTTPS_CODE) mais certbot renew --dry-run en échec"
           fi ;;
  *)       STATUS="certificat recréé mais HTTPS ne répond pas correctement (code ${HTTPS_CODE:-aucun})" ;;
esac
info "$STATUS"
[ "$DRYRUN_OK" = "oui" ] && [[ "$HTTPS_CODE" =~ ^[23] ]] || exit 2
exit 0
