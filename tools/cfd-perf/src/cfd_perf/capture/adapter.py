"""Pont Python → adaptateurs bash de `ADAPTATEUR/`.

Un adaptateur est un script bash autonome (mock.sh, OF.sh, …) qui implémente le
contrat de `ADAPTATEUR/interface.sh`. Cette classe le localise et appelle chaque
fonction `adapt_*` dans un sous-processus bash, en imposant une locale numérique
neutre pour que les nombres reviennent avec un point décimal.

Le solveur reste ainsi côté bash (code-agnostique, éditable par l'utilisateur) ;
l'orchestration, la génération du YAML et les tests restent côté Python.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ADAPTATEUR/ est à la racine du sous-projet : src/cfd_perf/capture/adapter.py
# -> parents[3] == tools/cfd-perf
ADAPTATEUR_DIR = Path(__file__).resolve().parents[3] / "ADAPTATEUR"

_DEFAULT_TIMEOUT_S = 120


class CaptureError(RuntimeError):
    """Échec d'un appel d'adaptateur, avec le contexte pour l'utilisateur."""


class BashAdapter:
    """Enveloppe typée autour d'un adaptateur bash.

    Résolution de l'identifiant : ``<dir>/<id>.sh`` puis ``<dir>/<id>/adaptateur.sh``
    (même convention que le framework).
    """

    def __init__(self, adapter_id: str, *, adapter_dir: Path | None = None) -> None:
        self.adapter_id = adapter_id
        self.adapter_dir = adapter_dir or ADAPTATEUR_DIR
        self.path = self._resolve()

    def _resolve(self) -> Path:
        flat = self.adapter_dir / f"{self.adapter_id}.sh"
        nested = self.adapter_dir / self.adapter_id / "adaptateur.sh"
        for candidate in (flat, nested):
            if candidate.is_file():
                return candidate
        raise CaptureError(
            f"adaptateur « {self.adapter_id} » introuvable dans {self.adapter_dir} "
            f"(cherché : {flat.name}, {self.adapter_id}/adaptateur.sh)"
        )

    # -- appel générique ----------------------------------------------------

    def _call(
        self,
        fn: str,
        *args: str | int,
        timeout: int = _DEFAULT_TIMEOUT_S,
    ) -> str:
        """Source l'adaptateur puis exécute ``fn args…`` ; renvoie stdout (strippé)."""
        env = dict(os.environ)
        env["LC_ALL"] = "C"  # point décimal, indépendant de la locale de l'hôte
        env["CFD_PERF_ADAPTATEUR_DIR"] = str(self.adapter_dir)

        cmd = [
            "bash",
            "-c",
            'source "$1"; fn="$2"; shift 2; "$fn" "$@"',
            "_",
            str(self.path),
            fn,
            *[str(a) for a in args],
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:  # bash absent
            raise CaptureError(f"bash introuvable : {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CaptureError(
                f"{self.adapter_id}:{fn} a dépassé le délai de {timeout}s"
            ) from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise CaptureError(
                f"{self.adapter_id}:{fn} a échoué (code {proc.returncode})"
                + (f" : {detail}" if detail else "")
            )
        return proc.stdout.strip()

    def _call_float(self, fn: str, *args: str | int) -> float:
        raw = self._call(fn, *args)
        try:
            return float(raw)
        except ValueError as exc:
            raise CaptureError(
                f"{self.adapter_id}:{fn} n'a pas renvoyé un nombre : {raw!r}"
            ) from exc

    def _call_int(self, fn: str, *args: str | int) -> int:
        raw = self._call(fn, *args)
        try:
            return int(float(raw))
        except ValueError as exc:
            raise CaptureError(
                f"{self.adapter_id}:{fn} n'a pas renvoyé un entier : {raw!r}"
            ) from exc

    # -- contrat ------------------------------------------------------------

    def nom(self) -> str:
        return self._call("adapt_nom")

    def verifier_installation(self) -> bool:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        proc = subprocess.run(
            ["bash", "-c", 'source "$1"; adapt_verifier_installation', "_", str(self.path)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return proc.returncode == 0

    def elements_a_copier(self) -> list[str]:
        out = self._call("adapt_liste_elements_a_copier")
        return [line.strip() for line in out.splitlines() if line.strip()]

    def preparer(self, run_dir: Path, cores: int) -> None:
        self._call("adapt_pilote_preparer", str(run_dir), cores)

    def soumettre(self, run_dir: Path, cores: int, queue: str | None = None) -> str:
        args: list[str | int] = [str(run_dir), cores]
        if queue:
            args.append(queue)
        job_id = self._call("adapt_pilote_soumettre", *args)
        if not job_id:
            raise CaptureError(
                f"{self.adapter_id}:adapt_pilote_soumettre n'a pas renvoyé d'identifiant de job"
            )
        return job_id

    def etat(self, run_dir: Path, job_id: str) -> str:
        return self._call("adapt_pilote_etat", str(run_dir), job_id)

    def temps_total_s(self, run_dir: Path) -> float:
        return self._call_float("adapt_pilote_temps_total", str(run_dir))

    def nb_iterations(self, run_dir: Path) -> int:
        return self._call_int("adapt_pilote_nb_iterations", str(run_dir))

    def ram_crete_gb(self, run_dir: Path, job_id: str) -> float | None:
        """RAM crête totale (Go), ou None si non mesurée (chaîne vide)."""
        raw = self._call("adapt_pilote_ram_crete", str(run_dir), job_id)
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError as exc:
            raise CaptureError(
                f"{self.adapter_id}:adapt_pilote_ram_crete valeur invalide : {raw!r}"
            ) from exc

    def nb_cellules(self, case_dir: Path) -> int:
        return self._call_int("adapt_maillage_nb_cellules", str(case_dir))

    def cible_iterations(self, case_dir: Path) -> int | None:
        raw = self._call("adapt_cible_iterations", str(case_dir))
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError as exc:
            raise CaptureError(
                f"{self.adapter_id}:adapt_cible_iterations valeur invalide : {raw!r}"
            ) from exc
