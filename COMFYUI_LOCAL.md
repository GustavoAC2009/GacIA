# ComfyUI local na Gac.IA

A Gac.IA se conecta ao ComfyUI pela API local (`http://127.0.0.1:8188`). Para novos usuários do Windows, o caminho recomendado é instalar o **ComfyUI Desktop oficial** em https://www.comfy.org/download. A Gac.IA abre essa página, mas não executa instaladores externos em silêncio.

1. Instale o ComfyUI Desktop pelo site oficial e abra o aplicativo.
2. Confirme que a API local está respondendo em `http://127.0.0.1:8188`.
3. Na Gac.IA, use `+` → `Gerar Imagens` e informe o nome exato de um checkpoint já instalado.
4. Para upscale, instale um modelo de super-resolução compatível em `models/upscale_models`; a Gac.IA lista os modelos reais disponibilizados pela API.

A instalação portátil oficial continua aceita para quem já a utiliza. A instalação portátil automática antiga permanece como mecanismo legado/avançado, não como recomendação padrão. A documentação oficial do ComfyUI afirma que Desktop é o caminho mais simples para começar e que Portable não é recomendado para usuários comuns. O Desktop tem suporte oficial AMD ROCm no Windows a partir da versão 0.7.0 para GPUs compatíveis. Para Intel e outros casos, não presuma aceleração pela GPU: a instalação manual oficial lista suporte a NVIDIA, AMD, Intel e outros tipos, mas pode exigir configuração específica. A disponibilidade real depende do modelo/driver/backend; CPU permanece alternativa quando o backend de GPU não estiver disponível.

**Modelos não estão incluídos:** checkpoints e modelos de upscale podem ser grandes, variam em licença e desempenho e não são baixados sem escolha do usuário. A resolução sugerida pela Gac.IA é apenas conservadora; não garante que qualquer workflow/modelo caiba na memória.

Fontes oficiais: https://github.com/Comfy-Org/ComfyUI#installing · https://www.comfy.org/download · https://blog.comfy.org/p/official-amd-rocm-support-arrives
