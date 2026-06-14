"""项目自定义异常体系。"""


class YbA2AError(Exception):
    """所有业务异常基类。"""


class PolicyParseError(YbA2AError):
    """政策文档解析失败。"""


class RuleExtractionError(YbA2AError):
    """规则抽取失败。"""


class DSLSyntaxError(YbA2AError):
    """DSL 规则语法错误。"""


class ModelInferenceError(YbA2AError):
    """模型推理调用失败。"""


class CrossRegionMismatchError(YbA2AError):
    """异地就医规则适配冲突。"""


class SimulationError(YbA2AError):
    """仿真推演失败。"""
