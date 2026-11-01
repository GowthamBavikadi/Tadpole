#!/usr/bin/env python3
# pet_main.py - Launcher for the Native macOS SwiftUI Liquid Glass Desktop Pet (bin/BrainPet)
import os
import sys
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SWIFT_SRC = os.path.join(ROOT_DIR, "src", "BrainPet.swift")
NATIVE_BIN = os.path.join(ROOT_DIR, "bin", "BrainPet")


def main():
    os.chdir(ROOT_DIR)
    # Automatically compile or update the native SwiftUI Liquid Glass binary if needed
    if not os.path.exists(NATIVE_BIN) or (
        os.path.exists(SWIFT_SRC) and os.path.getmtime(SWIFT_SRC) > os.path.getmtime(NATIVE_BIN)
    ):
        os.makedirs(os.path.dirname(NATIVE_BIN), exist_ok=True)
        print("Building native macOS SwiftUI Liquid Glass app...")
        subprocess.run(["/usr/bin/swiftc", "-O", SWIFT_SRC, "-o", NATIVE_BIN], check=True)

    if os.path.exists(NATIVE_BIN):
        print("----------------------------------------------------")
        print("Brain Desktop Pet - Native macOS Liquid Glass")
        print(" * Flick and throw the pet across your Terminal window (60 FPS bounce physics).")
        print(" * Click the pet to open the native Apple Liquid Glass HUD.")
        print("----------------------------------------------------")
        os.execv(NATIVE_BIN, [NATIVE_BIN])


if __name__ == "__main__":
    main()
