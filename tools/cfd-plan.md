# Plan de développement - Module CFD Statistics

## Vue d'ensemble du projet

Module Python professionnel pour l'analyse automatique de convergence et statistiques sur données CFD avec interface CLI moderne.

---

## Architecture du projet

```
cfd_statistics/
├── pyproject.toml                 # Configuration projet (Poetry/pip)
├── README.md                      # Documentation utilisateur
├── requirements.txt               # Dépendances
├── setup.py                       # Installation
│
├── statistics/
│   ├── __init__.py               # Exports principaux
│   ├── __version__.py            # Version du package
│   │
│   ├── cli.py                    # Interface ligne de commande (Typer/Click)
│   ├── config.py                 # Configuration et constantes
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── convergence.py        # Analyse de convergence
│   │   ├── periodicity.py        # Détection de périodicité (FFT, autocorr)
│   │   ├── moments.py            # Calcul moments statistiques
│   │   └── quality.py            # Métriques de qualité des données
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── detector.py           # Détection auto transitoire/périodique
│   │   ├── phase_average.py     # Phase-locked averaging
│   │   └── family_compare.py    # Comparaison entre familles
│   │
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── console.py            # Affichage rich console
│   │   ├── summary.py            # Génération résumés texte
│   │   ├── html.py               # Export HTML (optionnel)
│   │   └── templates/            # Templates de rapports
│   │
│   └── utils/
│       ├── __init__.py
│       ├── dataframe.py          # Helpers pandas
│       └── validation.py         # Validation des inputs
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Fixtures pytest
│   ├── test_convergence.py
│   ├── test_periodicity.py
│   └── test_cli.py
│
└── examples/
    ├── example_data.csv          # Données d'exemple
    └── example_usage.py          # Exemples d'utilisation
```

---

## Spécifications détaillées

### 1. CLI Interface (`cli.py`)

**Framework:** Typer (moderne, avec auto-complétion)

**Commandes principales:**

```bash
# Analyse complète automatique
cfd-stats analyze data.csv --output-dir results/

# Analyse par famille
cfd-stats analyze data.csv --family "RANS-SST"

# Export formats multiples
cfd-stats analyze data.csv --format html --format json --format txt

# Mode interactif
cfd-stats interactive data.csv

# Génération de rapport complet
cfd-stats report data.csv --template full

# Comparaison de familles
cfd-stats compare data.csv --families "RANS-SST,LES,DES"

# Mode watch (surveillance continue)
cfd-stats watch data.csv --refresh 10s
```

**Options globales:**
- `--verbose / -v`: Niveau de verbosité (0-3)
- `--output-dir / -o`: Répertoire de sortie
- `--config / -c`: Fichier de configuration YAML
- `--no-plots`: Désactive génération figures
- `--format`: Format de sortie (txt, html, json, markdown)

**Affichage Rich:**
- Progress bars pour analyses longues
- Tables formatées pour résultats
- Syntax highlighting pour logs
- Panels avec bordures pour sections
- Spinners pendant calculs

---

### 2. Module Core - Convergence (`core/convergence.py`)

**Classe principale:** `ConvergenceAnalyzer`

**Fonctionnalités:**

```python
class ConvergenceAnalyzer:
    """Analyse de convergence pour séries temporelles CFD"""
    
    def __init__(self, df: pd.DataFrame, iter_col: str = "iter"):
        """
        Parameters
        ----------
        df : DataFrame avec colonnes de coefficients et itérations
        iter_col : Nom de la colonne d'itération/temps
        """
        
    def detect_regime(self, coeff_col: str) -> dict:
        """
        Détecte automatiquement:
        - Phase transitoire
        - Phase convergée/périodique
        - Type d'évolution (monotone, oscillant, divergent)
        
        Returns
        -------
        {
            'regime': 'converged' | 'periodic' | 'diverging' | 'transient',
            'transient_end_iter': int,
            'is_steady': bool,
            'quality_score': float  # 0-100
        }
        """
        
    def compute_convergence_metrics(self, coeff_col: str) -> dict:
        """
        Métriques de convergence:
        - Taux de convergence (pente log-residual)
        - Nombre d'itérations au plateau
        - Variance des N dernières iterations
        - Critère de Cauchy
        
        Returns
        -------
        {
            'convergence_rate': float,
            'plateau_iterations': int,
            'final_variance': float,
            'cauchy_criterion': float,
            'is_converged': bool
        }
        """
        
    def sliding_statistics(self, coeff_col: str, window_size: int = 100) -> pd.DataFrame:
        """
        Statistiques glissantes:
        - Moyenne mobile
        - Écart-type mobile
        - Min/Max mobile
        
        Returns
        -------
        DataFrame avec colonnes: mean, std, min, max, variance_ratio
        """
```

---

### 3. Module Core - Périodicité (`core/periodicity.py`)

**Classe principale:** `PeriodicityDetector`

```python
class PeriodicityDetector:
    """Détection et analyse de périodicité"""
    
    def __init__(self, signal: np.ndarray, time: np.ndarray):
        """
        Parameters
        ----------
        signal : Valeurs du coefficient
        time : Temps ou itérations
        """
        
    def detect_period_fft(self) -> dict:
        """
        Détection par FFT
        
        Returns
        -------
        {
            'period': float,
            'frequency': float,
            'dominant_frequencies': List[float],  # Top 5
            'power_spectrum': np.ndarray,
            'freq_array': np.ndarray,
            'is_periodic': bool,
            'confidence': float  # 0-1
        }
        """
        
    def detect_period_autocorr(self) -> dict:
        """
        Détection par autocorrélation
        
        Returns
        -------
        {
            'period': float,
            'autocorr': np.ndarray,
            'lags': np.ndarray,
            'peaks': List[float],  # Périodes multiples
            'confidence': float
        }
        """
        
    def validate_periodicity(self, n_periods_required: int = 10) -> dict:
        """
        Validation qualité:
        - Nombre de périodes disponibles
        - Stabilité de la période
        - Cohérence FFT vs autocorr
        
        Returns
        -------
        {
            'n_periods_available': float,
            'is_sufficient': bool,
            'period_stability': float,  # coefficient of variation
            'quality_flag': 'excellent' | 'good' | 'poor' | 'insufficient'
        }
        """
        
    def extract_phase_locked_cycles(self) -> np.ndarray:
        """
        Extrait cycles individuels alignés en phase
        
        Returns
        -------
        Array shape (n_cycles, n_points_per_cycle)
        """
```

---

### 4. Module Core - Moments (`core/moments.py`)

**Classe principale:** `MomentCalculator`

```python
class MomentCalculator:
    """Calcul de tous les moments statistiques"""
    
    def __init__(self, data: np.ndarray, weights: Optional[np.ndarray] = None):
        """
        Parameters
        ----------
        data : Échantillon de données
        weights : Poids optionnels pour moyenne pondérée
        """
        
    def compute_all_moments(self, max_order: int = 4) -> dict:
        """
        Calcule tous les moments jusqu'à l'ordre spécifié
        
        Returns
        -------
        {
            'mean': float,
            'variance': float,
            'std': float,
            'skewness': float,
            'kurtosis': float,
            'excess_kurtosis': float,
            'higher_moments': {2: ..., 3: ..., 4: ...},
            'raw_moments': {...},
            'central_moments': {...}
        }
        """
        
    def compute_robust_statistics(self) -> dict:
        """
        Statistiques robustes aux outliers
        
        Returns
        -------
        {
            'median': float,
            'mad': float,  # Median Absolute Deviation
            'iqr': float,  # Interquartile Range
            'q25': float,
            'q75': float,
            'q95': float,
            'q99': float,
            'trimmed_mean_5': float,  # 5% trimmed
            'winsorized_mean': float
        }
        """
        
    def compute_confidence_intervals(self, confidence: float = 0.95) -> dict:
        """
        Intervalles de confiance bootstrap
        
        Returns
        -------
        {
            'mean_ci': (lower, upper),
            'std_ci': (lower, upper),
            'median_ci': (lower, upper)
        }
        """
        
    def goodness_of_fit(self) -> dict:
        """
        Tests de normalité et ajustement
        
        Returns
        -------
        {
            'shapiro_wilk': {'statistic': float, 'p_value': float},
            'anderson_darling': {...},
            'kolmogorov_smirnov': {...},
            'jarque_bera': {...},
            'is_normal': bool,
            'recommended_distribution': str  # 'normal', 'lognormal', etc.
        }
        """
```

---

### 5. Module Analysis - Détecteur (`analysis/detector.py`)

**Classe principale:** `AutomaticDetector`

```python
class AutomaticDetector:
    """Détection automatique du régime d'écoulement"""
    
    def __init__(self, df: pd.DataFrame, coeff_cols: List[str], iter_col: str = "iter"):
        pass
        
    def run_full_analysis(self) -> dict:
        """
        Pipeline complet d'analyse automatique
        
        Returns
        -------
        {
            'per_coefficient': {
                'coeff1': {
                    'regime': ...,
                    'convergence': {...},
                    'periodicity': {...},
                    'moments': {...},
                    'quality': {...}
                },
                ...
            },
            'global_assessment': {
                'overall_regime': str,
                'all_converged': bool,
                'recommendation': str
            }
        }
        """
        
    def detect_transient_end(self, signal: np.ndarray) -> int:
        """
        Détecte automatiquement la fin du transitoire
        
        Méthodes:
        - Cumulative sum (CUSUM)
        - Change point detection
        - Variance ratio test
        
        Returns
        -------
        Index de fin de transitoire
        """
```

---

### 6. Module Reports - Console (`reports/console.py`)

**Utilisation de Rich pour affichage professionnel**

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track
from rich.syntax import Syntax

class ConsoleReporter:
    """Génération de rapports console avec Rich"""
    
    def __init__(self):
        self.console = Console()
        
    def print_summary_table(self, results: dict):
        """
        Table résumé principal
        
        Colonnes:
        - Coefficient
        - Régime
        - Moyenne
        - Écart-type
        - Min/Max
        - Qualité
        """
        
    def print_convergence_panel(self, conv_data: dict):
        """Panel détaillé convergence avec code couleur"""
        
    def print_periodicity_analysis(self, period_data: dict):
        """
        Affichage analyse périodicité:
        - Période détectée
        - Fréquence
        - Nombre de périodes
        - Spectre de puissance (ASCII art)
        """
        
    def print_moments_detailed(self, moments: dict):
        """
        Table des moments:
        - Ordre 1-4
        - Statistiques robustes
        - Intervalles de confiance
        """
        
    def print_recommendations(self, recommendations: List[str]):
        """
        Panel avec recommandations expert:
        - Actions à prendre
        - Avertissements
        - Code couleur (vert/jaune/rouge)
        """
```

---

### 7. Configuration (`config.py`)

```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class AnalysisConfig:
    """Configuration globale de l'analyse"""
    
    # Détection de convergence
    convergence_threshold: float = 1e-6
    plateau_window: int = 100
    
    # Périodicité
    min_periods_required: int = 10
    fft_confidence_threshold: float = 0.7
    autocorr_threshold: float = 0.5
    
    # Statistiques
    confidence_level: float = 0.95
    bootstrap_samples: int = 1000
    max_moment_order: int = 4
    
    # Qualité
    quality_thresholds: Dict[str, float] = None
    
    # Plotting (interface avec votre package)
    plot_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.quality_thresholds is None:
            self.quality_thresholds = {
                'excellent': 0.95,
                'good': 0.80,
                'acceptable': 0.60,
                'poor': 0.40
            }
            
    @classmethod
    def from_yaml(cls, filepath: str) -> 'AnalysisConfig':
        """Charge configuration depuis YAML"""
        pass
```

---

### 8. Structure de données de sortie

**Format JSON standardisé:**

```json
{
  "metadata": {
    "analysis_date": "2024-01-15T10:30:00",
    "version": "1.0.0",
    "input_file": "data.csv",
    "n_coefficients": 5,
    "n_iterations": 10000
  },
  
  "global": {
    "regime": "periodic",
    "all_converged": false,
    "quality_score": 87.5,
    "recommendation": "Passage en URANS recommandé"
  },
  
  "per_coefficient": {
    "Cl": {
      "regime": {
        "type": "periodic",
        "transient_end": 2500,
        "quality": "good"
      },
      
      "convergence": {
        "is_converged": false,
        "rate": -0.0023,
        "plateau_iters": 5000,
        "final_variance": 1.2e-5
      },
      
      "periodicity": {
        "detected": true,
        "period": 125.3,
        "frequency": 0.00798,
        "n_periods": 42.5,
        "confidence": 0.92,
        "method": "autocorrelation"
      },
      
      "moments": {
        "mean": 0.523456,
        "std": 0.001234,
        "variance": 1.523e-6,
        "skewness": -0.123,
        "kurtosis": 2.987,
        "median": 0.523401,
        "min": 0.520123,
        "max": 0.526789,
        "percentiles": {
          "5": 0.521234,
          "25": 0.522345,
          "75": 0.524567,
          "95": 0.525678
        },
        "confidence_intervals": {
          "mean": [0.523123, 0.523789],
          "std": [0.001100, 0.001368]
        }
      },
      
      "quality": {
        "data_completeness": 100.0,
        "outliers_detected": 3,
        "outlier_percentage": 0.03,
        "is_normal": false,
        "recommended_distribution": "beta"
      }
    }
  },
  
  "family_comparison": {
    "RANS-SST": {
      "n_coefficients": 3,
      "mean_Cl": 0.523,
      "std_Cl": 0.0012
    }
  }
}
```

---

## Workflow d'implémentation

### Phase 1: Setup et Structure (2h)
1. Créer structure de dossiers
2. Setup `pyproject.toml` et dépendances
3. Initialiser tests pytest
4. Créer `__init__.py` avec exports

### Phase 2: Core Modules (6h)
1. Implémenter `convergence.py`
2. Implémenter `periodicity.py`
3. Implémenter `moments.py`
4. Tests unitaires pour chaque module

### Phase 3: Analysis Layer (4h)
1. Créer `detector.py` avec pipeline auto
2. Implémenter `phase_average.py`
3. Tests d'intégration

### Phase 4: CLI & Reports (4h)
1. Construire interface Typer dans `cli.py`
2. Créer `console.py` avec Rich
3. Templates de rapports
4. Tests CLI

### Phase 5: Integration & Polish (2h)
1. Intégration avec package `plotting`
2. Documentation docstrings
3. README complet
4. Examples

---

## Dépendances

```toml
[tool.poetry.dependencies]
python = "^3.9"
pandas = "^2.0"
numpy = "^1.24"
scipy = "^1.11"
rich = "^13.0"
typer = "^0.9"
pyyaml = "^6.0"
pydantic = "^2.0"  # Pour validation config

[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"
mypy = "^1.5"

[tool.poetry.group.plotting]
# Votre package custom
plotting = {path = "../plotting", develop = true}
```

---

## Interface avec votre package plotting

```python
# Dans statistics/reports/plotter.py

from plotting import Figure, Subplot  # Adapter selon votre API

class StatisticsPlotter:
    """Génération de figures via votre package plotting"""
    
    def plot_convergence_history(self, df: pd.DataFrame, coeff_col: str) -> Figure:
        """
        Figure convergence:
        - Subplot 1: Evolution temporelle
        - Subplot 2: Log des résidus
        - Subplot 3: Variance glissante
        """
        
    def plot_periodicity_analysis(self, period_data: dict) -> Figure:
        """
        Figure périodicité:
        - Subplot 1: Signal temporel avec périodes marquées
        - Subplot 2: Spectre FFT
        - Subplot 3: Autocorrélation
        - Subplot 4: Cycle moyen phase-locked
        """
        
    def plot_statistical_distribution(self, data: np.ndarray, moments: dict) -> Figure:
        """
        Figure distribution:
        - Histogramme + KDE
        - Q-Q plot
        - Box plot
        - Moments annotés
        """
        
    def plot_family_comparison(self, family_data: Dict[str, pd.DataFrame]) -> Figure:
        """Comparaison multi-familles"""
```

---

## Exemples d'utilisation

### CLI

```bash
# Analyse automatique complète
cfd-stats analyze simulation_results.csv \
  --output-dir ./analysis_results \
  --format html \
  --format json \
  --verbose

# Analyse d'une famille spécifique
cfd-stats analyze data.csv --family "RANS-SST" --plots

# Mode interactif
cfd-stats interactive data.csv

# Comparaison de familles
cfd-stats compare data.csv \
  --families "RANS,LES,DES" \
  --metric Cl \
  --output comparison_report.html
```

### API Python

```python
from statistics import ConvergenceAnalyzer, PeriodicityDetector, MomentCalculator
from statistics.analysis import AutomaticDetector
from statistics.reports import ConsoleReporter
import pandas as pd

# Chargement données
df = pd.read_csv("simulation.csv")

# Analyse automatique
detector = AutomaticDetector(
    df=df,
    coeff_cols=["Cl", "Cd", "Cm"],
    iter_col="iter"
)

results = detector.run_full_analysis()

# Affichage console professionnel
reporter = ConsoleReporter()
reporter.print_summary_table(results)
reporter.print_recommendations(results['recommendations'])

# Export
results.to_json("results.json")
results.to_html("report.html")

# Analyse manuelle détaillée
analyzer = ConvergenceAnalyzer(df, iter_col="iter")
conv_metrics = analyzer.compute_convergence_metrics("Cl")

# Détection périodicité
period_detector = PeriodicityDetector(
    signal=df["Cl"].values,
    time=df["iter"].values
)
period_info = period_detector.detect_period_autocorr()

if period_info['is_periodic']:
    # Calcul moments sur partie périodique
    transient_end = analyzer.detect_regime("Cl")['transient_end_iter']
    steady_data = df[df["iter"] > transient_end]["Cl"].values
    
    calc = MomentCalculator(steady_data)
    moments = calc.compute_all_moments(max_order=4)
    robust_stats = calc.compute_robust_statistics()
    
    print(f"Cl moyen: {moments['mean']:.6f} ± {moments['std']:.6f}")
    print(f"Période: {period_info['period']:.2f} itérations")
```

---

## Tests à implémenter

```python
# tests/test_convergence.py

def test_detect_converged_signal():
    """Test détection signal convergé monotone"""
    
def test_detect_periodic_signal():
    """Test détection signal périodique pur"""
    
def test_detect_diverging_signal():
    """Test détection divergence"""

# tests/test_periodicity.py

def test_fft_detection_pure_sine():
    """Test FFT sur signal sinusoidal parfait"""
    
def test_autocorr_noisy_periodic():
    """Test autocorr sur signal périodique bruité"""

# tests/test_moments.py

def test_moments_normal_distribution():
    """Vérification moments sur distribution normale connue"""
    
def test_confidence_intervals():
    """Test intervalles de confiance bootstrap"""

# tests/test_cli.py

def test_cli_analyze_command():
    """Test commande CLI avec données fictives"""
```

---

## Points d'attention

### Performance
- Utiliser `numba` pour accélération calculs lourds (FFT, autocorr)
- Lazy loading des données (chunks pandas pour gros fichiers)
- Cache des résultats intermédiaires

### Robustesse
- Gestion des NaN / Inf dans données
- Validation schéma DataFrame (Pandera)
- Messages d'erreur explicites

### Extensibilité
- Plugin system pour nouvelles métriques
- Support multi-formats input (CSV, HDF5, Parquet)
- Export vers LaTeX pour publications

---

## Checklist de livraison

- [ ] Structure complète du projet
- [ ] Tous les modules core implémentés
- [ ] Tests unitaires > 80% coverage
- [ ] CLI fonctionnel avec toutes commandes
- [ ] Rich console output professionnel
- [ ] Intégration package plotting
- [ ] Documentation API complète
- [ ] README avec exemples
- [ ] Fichier de configuration YAML example
- [ ] Données d'exemple
- [ ] Script d'installation
- [ ] Gestion des erreurs robuste

---

## Extensions futures possibles

1. **Dashboard interactif** (Streamlit/Dash)
2. **Analyse spectrale avancée** (wavelets, HHT)
3. **Machine Learning** pour classification auto régimes
4. **Support multi-runs** (comparaison études paramétriques)
5. **Export LaTeX** automatique pour papers
6. **Intégration CI/CD** pour monitoring continu
7. **API REST** pour intégration workflow
8. **Support GPU** (CuPy) pour très gros datasets

---

## Estimation temps total

- **Phase 1**: 2h
- **Phase 2**: 6h
- **Phase 3**: 4h
- **Phase 4**: 4h
- **Phase 5**: 2h
- **Tests & Debug**: 4h
- **Documentation**: 2h

**Total**: ~24h de développement focused

---

## Commande de démarrage Cursor

```bash
# Créer la structure
mkdir -p statistics/{core,analysis,reports,utils}
touch statistics/{__init__,__version__,cli,config}.py
touch statistics/core/{__init__,convergence,periodicity,moments,quality}.py
touch statistics/analysis/{__init__,detector,phase_average,family_compare}.py
touch statistics/reports/{__init__,console,summary,html}.py
touch statistics/utils/{__init__,dataframe,validation}.py

# Initialiser pyproject.toml
poetry init

# Installer dépendances
poetry add pandas numpy scipy rich typer pyyaml pydantic
poetry add --group dev pytest pytest-cov black ruff mypy
```

---

**Note pour Cursor**: Ce plan est conçu pour être implémenté module par module. Commencer par `core/convergence.py`, puis `core/periodicity.py`, puis progresser vers les couches supérieures. Chaque module est indépendant et testable unitairement.