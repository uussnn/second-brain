#!/usr/bin/env bash
# Первичная настройка VPS для GEO-аудита (Ubuntu 24.04, 2 vCPU, 4 ГБ RAM).
#
# Что делает (раздел 11 брифа):
#   1. обновляет систему и включает автоматические обновления безопасности;
#   2. создаёт пользователя factory (sudo, docker) и переносит на него SSH-ключ;
#   3. оставляет вход только по SSH-ключу: root и пароли запрещены;
#   4. включает файрвол (SSH, 80, 443) и fail2ban;
#   5. создаёт swap;
#   6. ставит Docker и Docker Compose из репозитория Ubuntu, ограничивает логи;
#   7. проверяет доступ к Telegram, агрегатору моделей, Wildberries и реестрам пакетов.
#
# Запуск — под root, в первой SSH-сессии после создания сервера:
#   scp setup_server.sh root@<IP>:/root/ && ssh root@<IP> 'bash /root/setup_server.sh'
# Повторный запуск безопасен: каждый шаг проверяет, сделан ли он.
# Только проверка доступов (можно от любого пользователя):
#   bash setup_server.sh --check-only
#
# Настройки через переменные окружения (все необязательные):
#   FACTORY_USER   имя пользователя                 (factory)
#   SSH_PORT       порт SSH                          (22)
#   SSH_PUBKEY     публичный ключ; по умолчанию берётся из /root/.ssh/authorized_keys
#   SWAP_SIZE      размер swap                       (2G)
#   TIMEZONE       часовой пояс                      (Europe/Moscow)
#   DOCKER_MIRROR  зеркало Docker Hub, напр. https://mirror.gcr.io
#   AITUNNEL_API_KEY  если задан, проверяется и ключ, а не только доступ к API.
#                     Ключ не сохраняется и не выводится.
#
# ВАЖНО: не закрывайте текущую сессию, пока не войдёте в новой:
#   ssh -p <SSH_PORT> factory@<IP>

set -Eeuo pipefail
export LC_ALL=C.UTF-8  # printf выравнивает кириллицу по символам, а не байтам

FACTORY_USER="${FACTORY_USER:-factory}"
SSH_PORT="${SSH_PORT:-22}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
TIMEZONE="${TIMEZONE:-Europe/Moscow}"
DOCKER_MIRROR="${DOCKER_MIRROR:-}"
REPORT="/var/log/factory-access-check.txt"
SWAP_FAILED=0

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'die "команда упала на строке $LINENO: $BASH_COMMAND"' ERR

# ------------------------------------------------------------------ проверка доступов

# check <название> <url> [ожидаемые коды через |] [доп. аргументы curl...]
# Без списка кодов доступом считается любой HTTP-ответ: сервис отвечает,
# значит сеть и DNS в порядке (401/404 без токена — норма).
CHECK_FAILED=0
row() {  # выравнивание по символам: printf в bash считает ширину в байтах
  local name="$1" status="$2" info="$3"
  printf '  %s%*s %-11s %s\n' "$name" $(( 34 - ${#name} > 0 ? 34 - ${#name} : 0 )) '' "$status" "$info" | tee -a "$REPORT"
}
check() {
  local name="$1" url="$2" expect="${3:-}" out code time err
  shift 3 2>/dev/null || shift $#
  err="$(mktemp)"
  out=$(curl -sS -o /dev/null -w '%{http_code} %{time_total}' --max-time 15 \
        -A 'Mozilla/5.0 (X11; Linux x86_64) factory-access-check' "$@" "$url" 2>"$err") || true
  code="${out%% *}"; time="${out##* }"
  if [[ ! "$code" =~ ^[0-9]{3}$ || "$code" == "000" ]]; then
    row "$name" "НЕТ ДОСТУПА" "$(head -n1 "$err")"
    CHECK_FAILED=1
  elif [[ -n "$expect" && ! "$code" =~ ^($expect)$ ]]; then
    row "$name" "ВНИМАНИЕ" "HTTP $code (ожидался $expect), ${time}s"
    CHECK_FAILED=1
  else
    row "$name" "OK" "HTTP $code, ${time}s"
  fi
  rm -f "$err"
}

access_checks() {
  log "Проверка доступов"
  if [[ ! -w "$(dirname "$REPORT")" ]]; then REPORT="${TMPDIR:-/tmp}/factory-access-check.txt"; fi
  {
    echo "Проверка доступов: $(date -Is), $(hostname)"
    echo "Внешний IP: $(curl -s --max-time 5 https://ifconfig.me || echo 'не определён')"
  } | tee "$REPORT"

  echo "Telegram:" | tee -a "$REPORT"
  check "Bot API api.telegram.org"      "https://api.telegram.org/"
  echo "Агрегатор моделей:" | tee -a "$REPORT"
  check "AITUNNEL api.aitunnel.ru"      "https://api.aitunnel.ru/v1/models"
  if [[ -n "${AITUNNEL_API_KEY:-}" ]]; then
    check "AITUNNEL: ключ принят"         "https://api.aitunnel.ru/v1/models" "200" \
          -H "Authorization: Bearer ${AITUNNEL_API_KEY}"
  fi
  echo "Wildberries:" | tee -a "$REPORT"
  check "Сайт www.wildberries.ru"       "https://www.wildberries.ru/"
  check "Публичный поиск search.wb.ru"  "https://search.wb.ru/exactmatch/ru/common/v4/search?query=%D0%BF%D0%B0%D0%BB%D0%B0%D1%82%D0%BA%D0%B0&resultset=catalog&dest=-1257786&page=1" "200"
  check "Seller API content-api"        "https://content-api.wildberries.ru/ping"
  check "Seller API common-api"         "https://common-api.wildberries.ru/ping"
  echo "Пакеты и образы:" | tee -a "$REPORT"
  check "Docker Hub registry-1.docker.io" "https://registry-1.docker.io/v2/"
  if [[ -n "$DOCKER_MIRROR" ]]; then
    check "Зеркало Docker"                "${DOCKER_MIRROR%/}/v2/"
  fi
  check "PyPI pypi.org"                 "https://pypi.org/simple/pip/" "200"
  check "GitHub github.com"             "https://github.com/"

  if (( CHECK_FAILED )); then
    warn "есть недоступные сервисы — см. $REPORT"
  else
    ok "все сервисы доступны, отчёт: $REPORT"
  fi
}

if [[ "${1:-}" == "--check-only" ]]; then
  access_checks
  exit 0
fi

# ------------------------------------------------------------------ предварительные проверки

[[ $EUID -eq 0 ]] || die "запустите под root: sudo bash $0"
# shellcheck source=/dev/null
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || die "скрипт рассчитан на Ubuntu, а здесь ${PRETTY_NAME:-неизвестная ОС}"
[[ "${VERSION_ID:-}" == "24.04" ]] || warn "проверено на Ubuntu 24.04, здесь ${VERSION_ID:-?}"
if ! [[ "$SSH_PORT" =~ ^[0-9]+$ ]] || (( SSH_PORT < 1 || SSH_PORT > 65535 )); then die "SSH_PORT: $SSH_PORT"; fi
[[ "$FACTORY_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "FACTORY_USER: $FACTORY_USER"

# Ключ ищем до любых изменений: без ключа после настройки SSH на сервер не попасть.
if [[ -z "${SSH_PUBKEY:-}" ]]; then
  if [[ -s /root/.ssh/authorized_keys ]]; then
    SSH_PUBKEY="$(grep -E '^(ssh-(ed25519|rsa)|ecdsa-sha2-|sk-)' /root/.ssh/authorized_keys || true)"
  elif [[ -s "/home/$FACTORY_USER/.ssh/authorized_keys" ]]; then
    SSH_PUBKEY="$(cat "/home/$FACTORY_USER/.ssh/authorized_keys")"
  fi
fi
[[ -n "${SSH_PUBKEY:-}" ]] || die "нет SSH-ключа: добавьте его при создании сервера (он окажется в /root/.ssh/authorized_keys) или передайте SSH_PUBKEY='ssh-ed25519 ...'"
echo "$SSH_PUBKEY" | ssh-keygen -l -f - >/dev/null 2>&1 || die "SSH_PUBKEY не похож на публичный ключ"

export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

# ------------------------------------------------------------------ 1. обновления

log "1/7 Обновление системы"
"${APT[@]}" update
"${APT[@]}" full-upgrade
"${APT[@]}" install ca-certificates curl git make ufw fail2ban python3-systemd \
  unattended-upgrades python3 python3-venv jq
timedatectl set-timezone "$TIMEZONE"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
# Логи systemd не должны съесть небольшой диск
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/factory.conf <<'EOF'
[Journal]
SystemMaxUse=500M
EOF
systemctl restart systemd-journald
ok "система обновлена, часовой пояс $TIMEZONE, автообновления безопасности включены"

# ------------------------------------------------------------------ 2. пользователь

log "2/7 Пользователь $FACTORY_USER"
if ! id "$FACTORY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$FACTORY_USER" >/dev/null
  ok "создан"
else
  ok "уже есть"
fi
usermod -aG sudo "$FACTORY_USER"
# Пароля у пользователя нет (вход только по ключу), поэтому sudo без пароля
echo "$FACTORY_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$FACTORY_USER"
chmod 440 "/etc/sudoers.d/90-$FACTORY_USER"
visudo -cf "/etc/sudoers.d/90-$FACTORY_USER" >/dev/null || die "ошибка в sudoers"

home="$(getent passwd "$FACTORY_USER" | cut -d: -f6)"
install -d -m 700 -o "$FACTORY_USER" -g "$FACTORY_USER" "$home/.ssh"
touch "$home/.ssh/authorized_keys"
while IFS= read -r key; do
  [[ -z "$key" ]] && continue
  grep -qxF "$key" "$home/.ssh/authorized_keys" || echo "$key" >> "$home/.ssh/authorized_keys"
done <<< "$SSH_PUBKEY"
chown "$FACTORY_USER:$FACTORY_USER" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"
ok "ключей в authorized_keys: $(grep -c . "$home/.ssh/authorized_keys")"

# ------------------------------------------------------------------ 3. SSH

log "3/7 SSH: только ключи, без root"
# 00- читается раньше 50-cloud-init.conf, а в sshd действует первое значение
cat > /etc/ssh/sshd_config.d/00-factory.conf <<EOF
Port $SSH_PORT
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowUsers $FACTORY_USER
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
EOF
sshd -t || die "конфигурация sshd не прошла проверку, SSH не перезапущен"
effective="$(sshd -T -C user="$FACTORY_USER",host=localhost,addr=127.0.0.1 2>/dev/null)"
grep -qx "passwordauthentication no" <<< "$effective" || die "вход по паролю остался включён"
grep -qx "permitrootlogin no" <<< "$effective" || die "вход под root остался включён"

# ------------------------------------------------------------------ 4. файрвол и fail2ban
# Файрвол включаем до перезапуска SSH, чтобы новый порт уже был открыт.

log "4/7 Файрвол и fail2ban"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$SSH_PORT/tcp" comment 'ssh' >/dev/null
ufw allow 80/tcp comment 'http' >/dev/null
ufw allow 443/tcp comment 'https' >/dev/null
ufw allow 443/udp comment 'http3' >/dev/null
ufw --force enable >/dev/null
ok "ufw: открыты $SSH_PORT/tcp, 80/tcp, 443/tcp, 443/udp"

cat > /etc/fail2ban/jail.d/factory.local <<EOF
[DEFAULT]
backend  = systemd
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port    = $SSH_PORT
EOF
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban
sleep 2
fail2ban-client status sshd >/dev/null || die "fail2ban не поднял защиту sshd"
ok "fail2ban следит за SSH"

# В Ubuntu 24.04 SSH запускается через ssh.socket, порт берётся из sshd_config
systemctl daemon-reload
if systemctl is-enabled ssh.socket >/dev/null 2>&1; then
  systemctl restart ssh.socket
fi
systemctl restart ssh
ok "SSH перезапущен: порт $SSH_PORT, только ключи, вход для $FACTORY_USER"

# ------------------------------------------------------------------ 5. swap

log "5/7 Swap $SWAP_SIZE"
if swapon --show=NAME --noheadings | grep -q .; then
  ok "swap уже есть: $(swapon --show=NAME,SIZE --noheadings | tr -s ' ' | paste -sd ',')"
else
  make_swap() {  # $1 = fallocate | dd
    rm -f /swapfile
    if [[ "$1" == fallocate ]]; then
      fallocate -l "$SWAP_SIZE" /swapfile
    else
      dd if=/dev/zero of=/swapfile bs=1M count="$(numfmt --from=iec "$SWAP_SIZE" | awk '{print int($1/1048576)}')" status=none
    fi
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
  }
  # На части ФС файл от fallocate не годится для swap — тогда пишем нулями через dd
  if make_swap fallocate 2>/dev/null || make_swap dd; then
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    ok "создан /swapfile"
  else
    rm -f /swapfile
    SWAP_FAILED=1
    warn "swap создать не удалось (ФС или виртуализация не поддерживают swap-файл), продолжаю без него"
  fi
fi
cat > /etc/sysctl.d/90-factory.conf <<'EOF'
vm.swappiness = 10
EOF
sysctl -q --system

# ------------------------------------------------------------------ 6. Docker

log "6/7 Docker"
# Пакеты из репозитория Ubuntu: не зависим от download.docker.com
"${APT[@]}" install docker.io docker-compose-v2
mkdir -p /etc/docker
if [[ -n "$DOCKER_MIRROR" ]]; then
  mirrors="[\"${DOCKER_MIRROR%/}\"]"
else
  mirrors="[]"
fi
jq -n --argjson m "$mirrors" '{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "live-restore": true,
  "registry-mirrors": $m
}' > /etc/docker/daemon.json
systemctl enable docker >/dev/null 2>&1
systemctl restart docker
usermod -aG docker "$FACTORY_USER"
docker version --format '{{.Server.Version}}' >/dev/null || die "Docker не запустился"
docker compose version >/dev/null || die "нет docker compose"
ok "Docker $(docker version --format '{{.Server.Version}}'), $(docker compose version --short 2>/dev/null | sed 's/^/Compose /')"
warn "порты, опубликованные контейнерами, обходят ufw: публикуйте наружу только 80/443 (Caddy)"

# ------------------------------------------------------------------ 7. доступы

access_checks

if (( SWAP_FAILED )); then
  SWAP_STATE="НЕ СОЗДАН — см. предупреждение выше"
else
  SWAP_STATE="$(swapon --show=NAME,SIZE --noheadings | tr -s ' ' | paste -sd ',')"
fi

log "Готово"
cat <<EOF
    Пользователь: $FACTORY_USER (sudo без пароля, группа docker)
    SSH:          порт $SSH_PORT, только ключ; root и пароли запрещены
    Файрвол:      $SSH_PORT/tcp, 80/tcp, 443/tcp, 443/udp
    Swap:         $SWAP_STATE
    Отчёт:        $REPORT

    Не закрывая эту сессию, проверьте вход в новой:
      ssh -p $SSH_PORT $FACTORY_USER@<IP>
EOF
