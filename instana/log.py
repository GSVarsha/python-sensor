from __future__ import print_function
import os
import sys
import logging

logger = None


def get_standard_logger():
    """
    Retrieves and configures a standard logger for the Instana package

    @return: Logger
    """
    standard_logger = logging.getLogger("instana")

    ch = logging.StreamHandler()
    f = logging.Formatter('%(asctime)s: %(process)d %(levelname)s %(name)s: %(message)s')
    ch.setFormatter(f)
    standard_logger.addHandler(ch)
    standard_logger.setLevel(logging.DEBUG)
    return standard_logger


def get_aws_lambda_logger():
    """
    Retrieves the preferred logger for AWS Lambda

    @return: Logger
    """
    aws_lambda_logger = logging.getLogger()
    aws_lambda_logger.setLevel(logging.INFO)
    return aws_lambda_logger


def running_in_gunicorn():
    """
    Determines if we are running inside of a gunicorn process and that the gunicorn logging package
    is available.

    @return:  Boolean
    """
    process_check = False
    package_check = False

    try:
        # Is this a gunicorn process?
        if hasattr(sys, 'argv'):
            for arg in sys.argv:
                if arg.find('gunicorn') >= 0:
                    process_check = True
        elif os.path.isfile("/proc/self/cmdline"):
            with open("/proc/self/cmdline") as cmd:
                contents = cmd.read()

            parts = contents.split('\0')
            parts.pop()
            cmdline = " ".join(parts)

            if cmdline.find('gunicorn') >= 0:
                process_check = True

        # Is the glogging package available?
        try:
            from gunicorn import glogging
        except ImportError:
            pass
        else:
            package_check = True

        # Both have to be true for gunicorn logging
        return process_check and package_check
    except Exception as e:
        print("Instana.log.running_in_gunicorn: %s", e, file=sys.stderr)
        return False


aws_env = os.environ.get("AWS_EXECUTION_ENV", "")
env_is_aws_lambda = "AWS_Lambda_" in aws_env

if running_in_gunicorn():
    logger = logging.getLogger("gunicorn.error")
elif env_is_aws_lambda is True:
    logger = get_aws_lambda_logger()
else:
    logger = get_standard_logger()
