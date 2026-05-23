"""
用户系统专用异常体系
"""
from fastapi import HTTPException, status


class UserServiceError(HTTPException):
    """用户服务基础异常"""
    def __init__(self, detail: str = "用户服务错误"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


class UserNotFoundError(UserServiceError):
    """用户不存在"""
    def __init__(self, detail: str = "用户不存在"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_404_NOT_FOUND


class UserNameConflictError(UserServiceError):
    """用户名冲突"""
    def __init__(self, detail: str = "用户名已存在"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_409_CONFLICT


class UserEmailConflictError(UserServiceError):
    """邮箱冲突"""
    def __init__(self, detail: str = "邮箱已被使用"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_409_CONFLICT


class InvalidCredentialsError(UserServiceError):
    """凭据无效（用户名或密码错误）"""
    def __init__(self, detail: str = "用户名或密码错误"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_401_UNAUTHORIZED


class AccountDisabledError(UserServiceError):
    """账户已被禁用"""
    def __init__(self, detail: str = "账户已被禁用"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_403_FORBIDDEN


class TokenInvalidError(UserServiceError):
    """令牌无效或已吊销"""
    def __init__(self, detail: str = "令牌无效或已过期"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_401_UNAUTHORIZED


class OldPasswordIncorrectError(UserServiceError):
    """旧密码不正确"""
    def __init__(self, detail: str = "当前密码不正确"):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_400_BAD_REQUEST
