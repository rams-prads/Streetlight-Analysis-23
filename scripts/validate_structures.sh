#!/usr/bin/env bash
# ==============================================================================
# Urban Integrated Municipal ERP — Structural & Code Consistency Validator
# Triggered automatically prior to git push or via manual check
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  URBAN ERP: PRE-PUSH STRUCTURAL VALIDATION GUARD     ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Verify Backend Directory Invariants
echo -e "\n${YELLOW}[1/4] Verifying Backend Architecture Structure...${NC}"
REQUIRED_BACKEND_DIRS=(
  "backend/services/core_service/app/api/v1"
  "backend/services/core_service/app/core"
  "backend/services/core_service/app/db"
  "backend/services/core_service/app/schemas"
)

for dir in "${REQUIRED_BACKEND_DIRS[@]}"; do
  if [ ! -d "$dir" ]; then
    echo -e "${RED}[ERROR] Required backend directory missing: $dir${NC}"
    echo -e "${RED}Push rejected. Please preserve required backend structure.${NC}"
    exit 1
  fi
done
echo -e "${GREEN}✓ Backend directory structure intact.${NC}"

# 2. Verify Backend Python Syntax & Compilation
echo -e "\n${YELLOW}[2/4] Verifying Python Compilation & Syntax...${NC}"
BACKEND_APP_DIR="$REPO_ROOT/backend/services/core_service/app"
PYTHON_FILES=$(find "$BACKEND_APP_DIR" -name "*.py")

for py_file in $PYTHON_FILES; do
  if ! python3 -m py_compile "$py_file"; then
    echo -e "${RED}[ERROR] Python syntax/compile error in: $py_file${NC}"
    echo -e "${RED}Push rejected. Fix Python syntax errors before pushing.${NC}"
    exit 1
  fi
done
echo -e "${GREEN}✓ All backend Python files compiled cleanly.${NC}"

# 3. Verify Frontend Directory Invariants
echo -e "\n${YELLOW}[3/4] Verifying Frontend Architecture Structure...${NC}"
REQUIRED_FRONTEND_DIRS=(
  "frontend/urban-console/src/app/core/models"
  "frontend/urban-console/src/app/core/services"
  "frontend/urban-console/src/app/shared/components"
  "frontend/urban-console/src/app/modules"
)

for dir in "${REQUIRED_FRONTEND_DIRS[@]}"; do
  if [ ! -d "$dir" ]; then
    echo -e "${RED}[ERROR] Required frontend directory missing: $dir${NC}"
    echo -e "${RED}Push rejected. Please preserve required Angular structure.${NC}"
    exit 1
  fi
done
echo -e "${GREEN}✓ Frontend directory structure intact.${NC}"

# 4. Verify Angular Build & TypeScript Compilation
echo -e "\n${YELLOW}[4/4] Validating Angular Build & TypeScript Compilation...${NC}"
cd "$REPO_ROOT/frontend/urban-console"
if ! HOME=/tmp CI=true npm run build; then
  echo -e "${RED}[ERROR] Angular build or TypeScript validation failed!${NC}"
  echo -e "${RED}Push rejected. Please fix frontend TypeScript/SCSS compilation issues.${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Angular frontend bundle compiled successfully.${NC}"

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}  ✓ ALL PRE-PUSH STRUCTURAL CHECKS PASSED SUCCESSFULLY${NC}"
echo -e "${GREEN}======================================================${NC}\n"
exit 0
