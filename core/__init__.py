"""@brief Package initialiser with lazy attribute loading so CPU worker processes avoid importing PyTorch."""

import importlib

__all__ = [
  "BraceAndCellResolver",
  "ConfigLoader",
  "GpuOcrEngine",
  "GraphicalElementDetector",
  "HeaderHierarchyResolver",
  "PagePreprocessor",
  "PlaceKeyNormaliser",
  "SectionAssembler",
  "TableDigitiserPipeline",
  "TableSeriesFlattener",
  "TableStructureReconstructor",
  "TokenSegmenter"
]


def __getattr__ (arg1_name):
  """
  @brief Lazily import class modules on demand to keep multiprocessing worker memory minimal.
  @param arg1_name Requested class attribute name.
  @return Imported class object.
  """
  #Convert from parameters
  name = arg1_name

  if name in __all__:
    mod = importlib.import_module(f"core.{name}")
    #Return statement
    return getattr(mod, name)

  raise AttributeError(f"module 'core' has no attribute {name!r}")
