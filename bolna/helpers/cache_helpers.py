import os
import json
from pathlib import Path
from bolna.constants import PREPROCESS_DIR


def save_preprocessed_data(assistant_id, conversation_type, preprocessed_data):
    if not os.path.exists(PREPROCESS_DIR):
        os.makedirs(PREPROCESS_DIR)

    agent_data_path = Path(PREPROCESS_DIR) / f"{assistant_id}_{conversation_type}.json"
    with open(agent_data_path, 'w') as fp:
        json.dump(preprocessed_data, fp)