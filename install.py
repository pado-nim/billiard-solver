"""설치 스크립트: 가상환경을 만들고 패키지를 설치한 뒤 바탕화면 바로가기를 만든다.
install.bat 이 이 파일을 실행한다.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
PY = os.path.join(VENV, "Scripts", "python.exe")


def step(msg):
    print("\n==> " + msg, flush=True)


def fail(msg):
    print("\n[설치 실패] " + msg)
    sys.exit(1)


def main():
    if sys.version_info < (3, 9):
        fail(f"Python 3.9 이상이 필요해요. 지금 버전: {sys.version.split()[0]}")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        fail("tkinter가 없어요. python.org 설치 프로그램에서 'tcl/tk and IDLE'을 체크하고 다시 설치하세요.")

    step("가상환경 만드는 중 (.venv)")
    if not os.path.exists(PY):
        subprocess.check_call([sys.executable, "-m", "venv", VENV])

    step("필요한 패키지 설치 중 (opencv, numpy, mss) - 1~2분 걸릴 수 있어요")
    subprocess.check_call([PY, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    subprocess.check_call([PY, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")])

    step("설치 확인")
    subprocess.check_call([PY, "-c", "import cv2, numpy, mss, tkinter; print('  모듈 OK')"], cwd=ROOT)

    step("바탕화면 바로가기 만드는 중")
    ps = r"""
$ws = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut((Join-Path $desk ($env:BS_NAME + '.lnk')))
$lnk.TargetPath = $env:BS_TARGET
$lnk.Arguments = $env:BS_ARGS
$lnk.WorkingDirectory = $env:BS_DIR
$lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,186"
$lnk.Save()
"""
    env = dict(os.environ, BS_NAME="당구 솔버", BS_TARGET=os.path.join(VENV, "Scripts", "pythonw.exe"),
               BS_ARGS="-m billiard_solver", BS_DIR=ROOT)
    try:
        subprocess.check_call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env)
        print("  바탕화면에 '당구 솔버' 바로가기를 만들었어요.")
    except Exception as e:
        print("  바로가기는 못 만들었어요 (run.bat을 직접 실행하면 돼요):", e)

    print("\n설치 완료!")
    print("  - 실행: 바탕화면 '당구 솔버' 또는 run.bat")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        fail(f"명령 실행 중 오류 ({e}). 인터넷 연결을 확인하고 install.bat을 다시 실행해 보세요.")
