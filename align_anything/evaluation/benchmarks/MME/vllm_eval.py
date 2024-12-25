# Copyright 2024 PKU-Alignment Team. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import argparse
import json
from align_anything.evaluation.inference.vllm_inference import *
from align_anything.evaluation.dataloader.base_dataloader import BaseDataLoader
from typing import List, Dict
from datasets import load_dataset, DatasetDict
from align_anything.utils.tools import read_eval_cfgs, dict_to_namedtuple, update_dict, custom_cfgs_to_dict, save_raw_outputs, load_raw_outputs
from align_anything.utils.template_registry import get_template_class
from align_anything.evaluation.data_type import InferenceInput, InferenceOutput
from align_anything.evaluation.eval_logger import EvalLogger
from collections import defaultdict
from tqdm import tqdm
import re

class MMEDataLoader(BaseDataLoader):
    def get_task_names(self):
        if isinstance(self.data_cfgs.task, list):
            return self.data_cfgs.task
        else:
            task_names = [
            self.data_cfgs.task
            ]
            return task_names

    def get_answer(self, data):
        return data['answer']
        
    def build_example_prompt(self, data, with_answer=True):
        prompt = f"This is a problem about {data['category']}.\n\n"
        return f"{prompt}{data['question']}"

    def build_prompt(self, data):
        assert self.num_shot == 0, "MME does not support few-shot learning."
        prompt = ""
        template = get_template_class(self.chat_template)
        question = [template.system_prompt + template.user_prompt.format(input=prompt + self.build_example_prompt(item, False)) + template.assistant_prompt.format(output="") for item in data]

        return question
    
    def preprocess(self, data):
        return self.build_prompt(data)
    
    def load_dataset(self, category_datasets) -> DatasetDict:
        processed_inputs = {}

        for task, dataset in category_datasets.items():
            prompts = self.preprocess(dataset)
            processed_inputs[task] = []
            for prompt, i in zip(prompts, range(len(dataset))):
                image, question_id, question = dataset[i]['image'], dataset[i]['question_id'], dataset[i]['question']
                processed_input = InferenceInput(text=prompt, image_file=image)
                processed_input.question_id = question_id + question
                processed_inputs[task].append(processed_input)
        return processed_inputs
    
    def get_category_datasets(self):
        dataset = load_dataset(self.task_dir, 'default')[self.split]

        category_datasets = defaultdict(list)
        for i in tqdm(range(len(dataset)), desc='Dataset classification'):
            category = dataset[i]['category']
            if category in self.task_names:
                category_datasets[category].append(dataset[i])
                
        return category_datasets
    
class MMEGeneratorVLLM(BaseInferencer_vllm):
    def eval(self, data:Dict[str, List[InferenceInput]], eval_configs) -> Dict[str, List[InferenceOutput]]:
        task2details = {}
        for task, input in data.items():
            raw_output = self.generation(input)
            for item in raw_output:
                item.prompt = re.sub(r"<image>", "", item.prompt)
                item.raw_output.prompt = re.sub(r"<image>", "", item.raw_output.prompt)
            task2details[task] = raw_output
        
        return task2details
    
    def _generation(self, inputs: List[InferenceInput]) -> List[InferenceOutput]:
        assert isinstance(inputs, list)
        InferenceOutputs = []
        outputs = self.model.generate([{"prompt": input.text, "multi_modal_data": {"image": input.image_file},} for input in inputs], sampling_params=self.samplingparams)
        InferenceOutputs = [InferenceOutput.from_vllm_output(question_id=input.question_id, vllm_output=output, store_raw=True) for output, input in zip(outputs, inputs)]
        return InferenceOutputs

def evaluator(test_dataset, output_data, file_path):
    num_match = 0
    num_match_plus = 0
    num_sum = 0
    question_id = set()
    for test_item in tqdm(test_dataset, desc="Evaluating"):
        for output_item in output_data:
            if test_item['question_id'] + test_item['question'] == output_item.question_id:
                num_sum += 1
                true_or_false = judger(test_item['answer'].lower(), output_item.response[0].lower())
                if true_or_false:
                    if test_item['question_id'] in question_id:
                        num_match_plus += 1
                    question_id.add(test_item['question_id'])
                    num_match += 1
                save_detail(test_item['question'], output_item.prompt, test_item['answer'].lower(), output_item.response[0].lower(), true_or_false, file_path)

    return (num_match / num_sum) * 100, (num_match_plus / (num_sum / 2)) * 100, num_sum

def judger(target, output):
    if target not in output:
        return False
    if "yes" in output and "no" not in output:
        return target == "yes"
    if "no" in output and "yes" not in output:
        return target == "no"
    last_yes = output.rfind('yes')
    last_no = output.rfind('no')
    if last_yes > last_no:
        return target == "yes"
    elif last_no > last_yes:
        return target == "no"
    return False

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _, unparsed_args = parser.parse_known_args()
    keys = [k[2:] for k in unparsed_args[0::2]]
    values = list(unparsed_args[1::2])
    unparsed_args = dict(zip(keys, values))

    dict_configs, infer_configs = read_eval_cfgs('mme', 'vLLM')

    try:
        assert dict_configs or infer_configs, "Config file does not exist or is incomplete."
    except AssertionError as e:
        print("Config file is not exist or incomplete.")
        exit()
    
    for k, v in unparsed_args.items():
        if v == '' or v is None:
            continue
        dict_configs = update_dict(dict_configs, custom_cfgs_to_dict(k, v))
        infer_configs = update_dict(infer_configs, custom_cfgs_to_dict(k, v))
    
    dict_configs, infer_configs = dict_to_namedtuple(dict_configs), dict_to_namedtuple(infer_configs)
    model_config = dict_configs.default.model_cfgs
    data_cfgs = dict_configs.default.data_cfgs
    eval_configs = dict_configs.default.eval_cfgs
    logger = EvalLogger('Evaluation', log_dir=eval_configs.output_dir)
    dataloader = MMEDataLoader(dict_configs)
    assert not (dataloader.num_shot > 0 or dataloader.cot), "Few-shot or chain-of-thought cannot be used for this benchmark."
    dataset = dataloader.get_category_datasets()
    test_data = dataloader.load_dataset(dataset)
    eval_module = MMEGeneratorVLLM(model_config, infer_configs)
    raw_outputs_dir = os.path.join(eval_configs.output_dir, f"raw_outputs_{re.sub(r'/', '_', model_config.model_name_or_path)}.pkl")
    if os.path.exists(raw_outputs_dir):
        raw_outputs = load_raw_outputs(raw_outputs_dir)
    else:
        raw_outputs = eval_module.eval(test_data, eval_configs)
        save_raw_outputs(raw_outputs, raw_outputs_dir)
    
    os.makedirs(logger.log_dir, exist_ok=True)
    uuid_path = f"{logger.log_dir}/{eval_configs.uuid}"
    os.makedirs(uuid_path, exist_ok=True)
    
    tot_score, tot_num_sum = 0.0, 0
    for task, test_data in dataset.items():
        file_path = f"{uuid_path}/{task}.json"
        acc, acc_plus, num_sum = evaluator(test_data, raw_outputs[task], file_path)
        score = acc + acc_plus
        tot_score += score
        tot_num_sum += num_sum

        output_dict = {
            'model_id': [dict_configs.default.model_cfgs.model_id],
            'num_sum': [num_sum],
            'acc': [acc],
            'acc_plus': [acc_plus],
            'score': [score]
        }
        logger.print_table(title=f'MME/{task} Benchmark', data=output_dict)
        logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        logger.log('info', f"task: {task}")
        logger.log('info', f"model_id: {output_dict['model_id'][0]},")
        logger.log('info', f"num_sum: {output_dict['num_sum'][0]},")
        logger.log('info', f"acc: {output_dict['acc'][0]},")
        logger.log('info', f"acc_plus: {output_dict['acc_plus'][0]},")
        logger.log('info', f"score: {output_dict['score'][0]},")
        logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')

    output_dict = {
        'model_id': [dict_configs.default.model_cfgs.model_id],
        'tot_num_sum': [tot_num_sum],
        'tot_score': [tot_score]
    }
    logger.print_table(title=f'MME Benchmark', data=output_dict)
    logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    logger.log('info', f"model_id: {output_dict['model_id'][0]},")
    logger.log('info', f"tot_num_sum: {output_dict['tot_num_sum'][0]},")
    logger.log('info', f"tot_score: {output_dict['tot_score'][0]},")
    logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    
if __name__ == '__main__':
    main()