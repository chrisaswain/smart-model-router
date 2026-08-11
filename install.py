"""Install the smart model router: link the skill, register the routing hook.

Run from anywhere:  python install.py         (add --uninstall to remove)

Idempotent. Backs up settings.json before touching it. Never overwrites an
existing hook block; it appends and de-duplicates.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SKILL_SRC = REPO / "skills" / "model-router"
HOOK = REPO / "hooks" / "routing_gate.py"
CLAUDE = Path.home() / ".claude"
SKILL_DST = CLAUDE / "skills" / "model-router"
SETTINGS = CLAUDE / "settings.json"
# Full interpreter path, not a bare "python": many machines (most macOS installs)
# have no `python` on PATH at all, and the hook would silently never fire.
COMMAND = f'"{sys.executable}" "{HOOK}"'


def link_skill():
    if SKILL_DST.exists() or SKILL_DST.is_symlink():
        print(f"  skill: already present at {SKILL_DST}, leaving it alone")
        return
    SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            # Junction: works without admin or Developer Mode, unlike a symlink.
            subprocess.run(["cmd", "/c", "mklink", "/J", str(SKILL_DST), str(SKILL_SRC)],
                           check=True, capture_output=True)
        else:
            SKILL_DST.symlink_to(SKILL_SRC, target_is_directory=True)
        print(f"  skill: linked {SKILL_DST} -> {SKILL_SRC}")
    except (subprocess.CalledProcessError, OSError):
        shutil.copytree(SKILL_SRC, SKILL_DST)
        print(f"  skill: COPIED to {SKILL_DST} (linking failed). This is a snapshot: "
              "`git pull` here will NOT update it. Delete that directory and re-run "
              "install.py to pick up a newer table.")


def load_settings():
    if not SETTINGS.exists():
        return {}
    with open(SETTINGS, encoding="utf-8") as fh:
        return json.load(fh)


def save_settings(data):
    if SETTINGS.exists():
        # Never overwrite an existing backup: the pristine pre-install copy is the
        # one worth keeping, and a second run would replace it with post-install
        # state, i.e. destroy the only thing the backup was for.
        backup = SETTINGS.with_suffix(".json.bak")
        n = 0
        while backup.exists():
            n += 1
            backup = SETTINGS.with_suffix(f".json.bak{n}")
        shutil.copy2(SETTINGS, backup)
        print(f"  settings: backed up to {backup}")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def register_hook(remove=False):
    data = load_settings()
    groups = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    # Our entry is identified by the hook filename, so a moved checkout still matches.
    def is_ours(h):
        return isinstance(h, dict) and "routing_gate.py" in str(h.get("command", ""))

    # Prune only groups WE emptied. A group the user already had with an empty
    # hooks list is their config, not our litter, and deleting it is data loss.
    kept = []
    for g in groups:
        had = list(g.get("hooks", []))
        g["hooks"] = [h for h in had if not is_ours(h)]
        if g["hooks"] or not had:
            kept.append(g)
    groups[:] = kept

    if not remove:
        entry = {"type": "command", "command": COMMAND, "timeout": 10}
        plain = next((g for g in groups if not g.get("matcher")), None)
        if plain:
            plain["hooks"].append(entry)
        else:
            groups.append({"matcher": "", "hooks": [entry]})

    if not groups:
        data["hooks"].pop("UserPromptSubmit", None)
        if not data["hooks"]:
            data.pop("hooks")
    save_settings(data)
    print(f"  hook: {'removed' if remove else 'registered'} -> {COMMAND}")


def verify():
    probe = json.dumps({"prompt": "refactor the auth module and make the failing tests pass"})
    out = subprocess.run([sys.executable, str(HOOK)], input=probe,
                         capture_output=True, text=True).stdout.strip()
    if not out:
        print("  verify: FAILED, the hook produced no output for a coding prompt")
        return False
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    print(f"  verify: OK\n\n{ctx}\n")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    if args.uninstall:
        print("Uninstalling smart-model-router:")
        register_hook(remove=True)
        # POSIX symlinks need unlink(); rmdir() raises NotADirectoryError on them.
        # Windows junctions are directories and need rmdir(). Removing a link never
        # touches the target, but a real directory here is a copytree fallback and
        # is the user's to delete.
        try:
            if SKILL_DST.is_symlink():
                SKILL_DST.unlink()
                print(f"  skill: unlinked {SKILL_DST}")
            elif os.name == "nt" and SKILL_DST.is_dir():
                # rmdir removes a junction; on a real populated copy it raises
                # WinError 145, which is the signal that this is the user's data
                # and not our link. (os.path.isjunction is cleaner but is 3.12+,
                # and INSTALL.md promises 3.9+.)
                try:
                    SKILL_DST.rmdir()
                    print(f"  skill: unlinked {SKILL_DST}")
                except OSError:
                    print(f"  skill: {SKILL_DST} is a real copy, not a link. "
                          "Delete it by hand if you want it gone.")
            elif SKILL_DST.exists():
                print(f"  skill: {SKILL_DST} is a real copy, not a link. "
                      "Delete it by hand if you want it gone.")
        except OSError as exc:
            print(f"  skill: could not remove {SKILL_DST} ({exc}); remove by hand")
        print("\nDone. Restart Claude Code.")
        return

    print("Installing smart-model-router:")
    link_skill()
    register_hook()
    ok = verify()
    print("Done. Restart Claude Code for the hook to take effect."
          if ok else "Install finished but verification failed; see above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
