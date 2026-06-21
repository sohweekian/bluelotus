# prompting package
# BlueLotus V3 Prompt Architecture Layer
#
# Modules:
#   context_builder      — builds agent-specific desk_context from dataset + operator pack
#   memory_retriever     — injects historical cycle memory into agent prompts
#   prompt_budgeter      — enforces char budget limits across prompt sections
#   prompt_compiler      — assembles final system + user prompts from universal + agent packs
#   retry_prompt_builder — generates failure-repair prompts for schema-invalid agent responses
