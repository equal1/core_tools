class DatasetError(Exception):
    pass


class InvalidNameError(DatasetError):
    pass


class NoScopeError(DatasetError):
    def __init__(self, project_name):
        super().__init__(f"No scope for project '{project_name}'")
