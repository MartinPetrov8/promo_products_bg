"""
PromoBG Matching Module

Cross-store product matching with category blocking.
"""

from .pipeline import CrossStoreMatcher, run_matching_pipeline

__all__ = ['CrossStoreMatcher', 'run_matching_pipeline']
