#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== RedTransporteAPI — Instalación ==="
echo ""

# --- Verificar Python ---
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON_CMD="$cmd"
            echo -e "${GREEN}✓${NC} Python encontrado: $("$cmd" --version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}✗${NC} Python 3.9+ no encontrado."
    echo ""
    echo "  Instalar Python:"
    echo "    Ubuntu/Debian:  sudo apt install python3 python3-pip"
    echo "    Fedora/RHEL:    sudo dnf install python3 python3-pip"
    echo "    macOS:          brew install python3"
    echo "    Arch:           sudo pacman -S python python-pip"
    exit 1
fi

# --- Preparar entorno virtual (evita PEP 668) ---
VENV_DIR="$HOME/.red-transporte/venv"
LOCAL_BIN="$HOME/.local/bin"

echo -e "${YELLOW}!${NC} Configurando entorno virtual en $VENV_DIR..."
mkdir -p "$(dirname "$VENV_DIR")"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null || {
        echo -e "${RED}✗${NC} No se pudo crear el entorno virtual."
        echo "  En Debian/Ubuntu instala: sudo apt install python3-venv"
        exit 1
    }
fi

PIP_CMD="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"

"$PIP_CMD" install --upgrade pip >/dev/null 2>&1 || true
echo -e "${GREEN}✓${NC} Entorno virtual listo: $VENV_DIR"

# --- Localizar o clonar el repositorio ---
REPO_URL="https://github.com/iiroak/RedTransporteAPI"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    cd "$SCRIPT_DIR"
    echo -e "${GREEN}✓${NC} Usando repo local: $SCRIPT_DIR"
elif [ -f "$(pwd)/pyproject.toml" ]; then
    echo -e "${GREEN}✓${NC} Usando repo local: $(pwd)"
else
    INSTALL_DIR="$HOME/.red-transporte-install"
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"

    if command -v git &>/dev/null; then
        echo -e "${YELLOW}!${NC} Clonando repositorio en $INSTALL_DIR..."
        git clone --depth=1 "$REPO_URL.git" "$INSTALL_DIR"
        echo -e "${GREEN}✓${NC} Repositorio clonado"
    else
        ZIP_URL="$REPO_URL/archive/refs/heads/main.zip"
        ZIP_TMP="$INSTALL_DIR/repo.zip"
        echo -e "${YELLOW}!${NC} git no encontrado, descargando ZIP..."

        if command -v curl &>/dev/null; then
            curl -sSL "$ZIP_URL" -o "$ZIP_TMP"
        elif command -v wget &>/dev/null; then
            wget -q "$ZIP_URL" -O "$ZIP_TMP"
        else
            echo -e "${RED}✗${NC} No se encontró curl ni wget para descargar el repositorio."
            exit 1
        fi

        if command -v unzip &>/dev/null; then
            unzip -q "$ZIP_TMP" -d "$INSTALL_DIR"
        else
            "$PYTHON_CMD" -c "import zipfile, sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP_TMP" "$INSTALL_DIR"
        fi

        EXTRACTED=$(find "$INSTALL_DIR" -maxdepth 1 -type d -name "RedTransporteAPI-*" | head -1)
        if [ -z "$EXTRACTED" ]; then
            echo -e "${RED}✗${NC} No se pudo localizar el directorio extraído."
            exit 1
        fi
        INSTALL_DIR="$EXTRACTED"
        echo -e "${GREEN}✓${NC} Repositorio descargado"
    fi

    cd "$INSTALL_DIR"
fi

# --- Instalar ---
echo ""
echo "¿Qué deseas instalar?"
echo "  1) Solo CLI (comando red-transporte)"
echo "  2) CLI + API HTTP (red-transporte + red-transporte-server)"
echo "  3) Todo (CLI + API + rich output + agent tools)"
echo ""
read -rp "Opción [3]: " INSTALL_MODE
INSTALL_MODE="${INSTALL_MODE:-3}"

case "$INSTALL_MODE" in
    1)
        echo "Instalando CLI..."
        "$PIP_CMD" install .
        ;;
    2)
        echo "Instalando CLI + API..."
        "$PIP_CMD" install ".[api]"
        ;;
    *)
        echo "Instalando todo..."
        "$PIP_CMD" install ".[all]"
        ;;
esac

echo ""

# --- Exponer comandos en ~/.local/bin ---
mkdir -p "$LOCAL_BIN"

if [ -x "$VENV_DIR/bin/red-transporte" ]; then
    ln -sf "$VENV_DIR/bin/red-transporte" "$LOCAL_BIN/red-transporte"
fi

if [ -x "$VENV_DIR/bin/red-transporte-server" ]; then
    ln -sf "$VENV_DIR/bin/red-transporte-server" "$LOCAL_BIN/red-transporte-server"
fi

echo -e "${GREEN}✓${NC} Comandos enlazados en $LOCAL_BIN"

# --- Verificar PATH ---
CMD_FOUND=false

if command -v red-transporte &>/dev/null; then
    CMD_FOUND=true
    echo -e "${GREEN}✓${NC} Comando 'red-transporte' disponible en PATH"
elif [ -f "$LOCAL_BIN/red-transporte" ]; then
    echo -e "${YELLOW}!${NC} 'red-transporte' instalado en $LOCAL_BIN pero no está en PATH"
fi

if [ "$CMD_FOUND" = false ]; then
    SHELL_RC=""
    if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "$(command -v zsh)" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "$(command -v bash)" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q "$LOCAL_BIN" "$SHELL_RC" 2>/dev/null; then
            echo ""
            read -rp "¿Agregar $LOCAL_BIN al PATH en $SHELL_RC? [S/n]: " ADD_PATH
            ADD_PATH="${ADD_PATH:-S}"
            if [[ "$ADD_PATH" =~ ^[Ss]$ ]]; then
                echo "" >> "$SHELL_RC"
                echo "# RedTransporteAPI" >> "$SHELL_RC"
                echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_RC"
                echo -e "${GREEN}✓${NC} PATH actualizado en $SHELL_RC"
                echo -e "${YELLOW}!${NC} Ejecuta: source $SHELL_RC"
            fi
        else
            echo -e "${GREEN}✓${NC} $LOCAL_BIN ya está en $SHELL_RC"
        fi
    else
        echo -e "${YELLOW}!${NC} Agrega manualmente a tu shell config:"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
fi

# --- Descargar GTFS ---
echo ""
read -rp "¿Descargar datos GTFS ahora? (~50MB desde DTPM) [S/n]: " DL_GTFS
DL_GTFS="${DL_GTFS:-S}"
if [[ "$DL_GTFS" =~ ^[Ss]$ ]]; then
    echo "Descargando GTFS..."
    "$VENV_DIR/bin/red-transporte" gtfs update 2>/dev/null || "$VENV_PYTHON" -m red_transporte_api gtfs update
fi

# --- Resultado ---
echo ""
echo "=== Instalación completa ==="
echo ""
echo "  Uso:"
echo "    red-transporte gtfs update           # Descargar datos GTFS"
echo "    red-transporte stop PA433            # Info de paradero"
echo "    red-transporte search providencia    # Buscar paraderos"
echo "    red-transporte nearby -33.45 -70.65  # Paraderos cercanos"
echo "    red-transporte station -33.45 -70.65 # Metro más cercano"
echo "    red-transporte predict PA433         # Predicciones en tiempo real"
echo "    red-transporte route 506             # Info de recorrido"
case "$INSTALL_MODE" in
    2|3)
        echo "    red-transporte server                # Iniciar API HTTP en :8000"
        ;;
esac
echo ""
