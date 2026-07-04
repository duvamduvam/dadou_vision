import os
import sys

# La racine du dépôt donne accès au package vision/ et, via le symlink
# dadou_utils_ros -> ../dadou_utils_ros, à la lib partagée du parc (pas
# utilisée par les tests unit/ actuels, mais gardée pour parité avec les
# autres dépôts dadou_*_ros au cas où V1/V2 en aient besoin).
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
