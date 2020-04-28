# Copyright © 2020, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All rights reserved.
#
# The DELTA (Deep Earth Learning, Tools, and Analysis) platform is
# licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Lists all avaiable commands.
"""
import delta.imagery.imagery_config
import delta.ml.ml_config

from . import classify, train, mlflow_ui

delta.imagery.imagery_config.register()
delta.ml.ml_config.register()

SETUP_COMMANDS = [train.setup_parser,
                  classify.setup_parser,
                  mlflow_ui.setup_parser,
                 ]
