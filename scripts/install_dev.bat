@echo off
REM Fait par Gillesto
REM install_dev.bat — Installation des dépendances Python SANS compiler Rust
REM
REM Usage : double-cliquer ou lancer depuis SafeRoute/
REM   scripts\install_dev.bat
REM
REM Ce script installe uniquement les dépendances Python pures.
REM Le core Rust (saferoute_core) sera compilé séparément avec maturin.

echo ============================================
echo  SafeRoute — Installation developpement
echo ============================================
echo.

REM Detecte python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR : python non trouve dans le PATH
    echo Installez Python 3.10+ depuis https://python.org
    pause
    exit /b 1
)

python --version
echo.

REM Installation des dependances Python pures (sans maturin/Rust)
echo [1/4] Installation des dependances principales...
python -m pip install --upgrade pip
python -m pip install osmnx networkx geopandas shapely scipy numpy fastapi "uvicorn[standard]" pydantic httpx matplotlib folium

echo.
echo [2/4] Installation des dependances de test...
python -m pip install pytest pytest-asyncio pytest-mock

echo.
echo [3/4] Ajout du package saferoute au path Python...
REM Installe le package en mode editable SANS build backend Rust
python -m pip install --no-build-isolation -e "bindings\python" --no-deps

echo.
echo [4/4] Verification de l'installation...
python -c "from saferoute import SafeRouteEngine; print('OK : SafeRouteEngine importe avec succes')"
python -c "from saferoute.graph_cache import GraphCache; print('OK : GraphCache importe avec succes')"
python -c "from saferoute.kde_scorer import compute_kde_scores; print('OK : KDE scorer importe avec succes')"

echo.
echo ============================================
echo  Installation terminee !
echo.
echo  Pour lancer les tests :
echo    python -m pytest tests/python/test_phase1.py -v
echo.
echo  Pour telecharger les graphes (necessite internet) :
echo    python scripts/download_cities.py
echo.
echo  Pour tester sans internet :
echo    python scripts/download_cities.py --offline
echo.
echo  Pour compiler le core Rust (necessite Rust installe) :
echo    pip install maturin
echo    cd bindings\python
echo    maturin develop --release
echo ============================================
pause
