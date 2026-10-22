"""Select GNU compilers without assuming Debian's version-suffixed names."""
import os
import shutil
import subprocess
import sys


def select_compiler(variable: str, names: tuple[str, ...], language: str) -> str:
    """Resolve CC/CXX or a default GCC executable and require GNU version 14+.

    Overrides must name one executable, not a shell command. Raise ValueError
    for missing compilers, Clang (which defines GNU compatibility macros), or
    old GCC. No installation or compiler setting is changed.
    """
    candidates = (os.environ[variable],) if os.environ.get(variable) else names
    errors = []
    for candidate in candidates:
        executable = shutil.which(candidate)
        if not executable:
            errors.append(f"{candidate}: not found")
            continue
        try:
            result = subprocess.run([executable, "-dM", "-E", "-x", language, "-"],
                                    input="", capture_output=True, text=True, check=True, timeout=15)
            macros = dict(line.split(maxsplit=2)[1:] for line in result.stdout.splitlines()
                          if line.startswith("#define ") and len(line.split(maxsplit=2)) == 3)
            if "__clang__" in macros or int(macros.get("__GNUC__", "0")) < 14:
                errors.append(f"{candidate}: requires GNU GCC 14 or newer")
                continue
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        return executable
    raise ValueError(f"No usable {variable} compiler. " + "; ".join(errors)
                     + ". On Arch install gcc; alternatively set CC/CXX to GCC 14+ executables.")


def select_toolchain() -> tuple[str, str]:
    """Return validated C and C++ compiler paths; respect explicit CC/CXX."""
    return (select_compiler("CC", ("gcc-14", "gcc"), "c"),
            select_compiler("CXX", ("g++-14", "g++"), "c++"))


if __name__ == "__main__":
    try:
        print("\n".join(select_toolchain()))
    except ValueError as exc:
        print(f"yt2slp: {exc}", file=sys.stderr)
        raise SystemExit(1)
