MODEL_NAME_OR_PATH="/home/pku0008/align-anything/output/rm/slice_end" # model path

TRAIN_DATASETS="../../datasets/PKU-SafeRLHF-single-dimension" # dataset path
TRAIN_TEMPLATE="PKUSafeRLHF" # dataset template
TRAIN_SPLIT="train" # split the dataset


EVAL_DATASETS="../../datasets/PKU-SafeRLHF-single-dimension" # dataset path
EVAL_TEMPLATE="HOMEWORK" # dataset template
EVAL_SPLIT="test" # split the dataset

OUTPUT_DIR="../output/rm" # output dir

# For wandb online logging
export WANDB_API_KEY="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"

# Source the setup script
source ./setup.sh

# Execute deepspeed command
deepspeed \
     --master_port ${MASTER_PORT} \
     --module align_anything.trainers.text_to_text.rm \
     --model_name_or_path ${MODEL_NAME_OR_PATH} \
     --eval_datasets ${EVAL_DATASETS} \
     --eval_template ${EVAL_TEMPLATE} \
     --eval_split ${EVAL_SPLIT} \
     --output_dir ${OUTPUT_DIR} \
     --save_interval 1000000 \
     --epochs 3