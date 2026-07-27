"""The pickles were written where sklearn's Cython loss module answered to the bare
name `_loss`. Alias it before unpickling, otherwise joblib.load raises
ModuleNotFoundError: No module named '_loss'."""
import sys
import sklearn._loss._loss as _cy_loss
import sklearn._loss.loss as _py_loss
import sklearn._loss.link as _link

sys.modules.setdefault('_loss', _cy_loss)
sys.modules.setdefault('_loss._loss', _cy_loss)
sys.modules.setdefault('_loss.loss', _py_loss)
sys.modules.setdefault('_loss.link', _link)
