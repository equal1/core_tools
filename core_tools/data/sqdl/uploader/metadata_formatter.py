import logging
import re

from .exceptions import InvalidNameError

logger = logging.getLogger(__name__)


class MetadataFormatter:
    def __init__(self):
        self.str_pattern = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-.,:()[\]* ]*$")

    def validate(self, s: str | list[str]):
        if isinstance(s, str):
            if len(s) < 1:
                raise InvalidNameError(f"Name {s} is too short. ")
            if len(s) > 40:
                raise InvalidNameError(f"Name '{s}' too long")
            if not self.str_pattern.match(s):
                logger.warning(f'Invalid string {s} in metadata')
                return '__invalid__'
            return s
        else:
            return [self.validate(v) for v in s]

    def format(self, desc: dict[str, str | list[str]]):
        '''
        Using schema:
        measurement_data(
            setup(min_length=2, type=str),
            sample(min_length=2),
            variables_measured(type=list),
            dimensions(type=list))
        '''
        setup = desc['setup']
        # Fix exported data
        if setup[-1] == ',':
            setup = setup[:-1]

        metadata = {
            'data_type': 'measurement_data',
            'setup': self.validate(setup),
            'sample': self.validate(desc['sample']),
            'variables_measured': self.validate(desc['vars']),
            'dimensions': self.validate(desc['dims']),
            # TODO more metadata ?
            "fridge": "test-parameter",  # todo: 
        }
        if "project" in desc:
            metadata["project"] = desc["project"]
        return metadata
