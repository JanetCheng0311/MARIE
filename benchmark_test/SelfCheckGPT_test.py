from selfcheckgpt.modeling_selfcheck import SelfCheckMQAG
import torch
import spacy

# Your text to check (GPT output)
passage = "港鐵繼續提供八達通付款服務可以喺港鐵站、巴士同便利店付款，非常方便 ；天文台預測今個冬天氣溫偏低，但唔會落雪；而政府持續推動創新科技發展，探索太空相關研究計劃。"

# Split into sentences
nlp = spacy.load("en_core_web_sm")
sentences = [sent.text.strip() for sent in nlp(passage).sents]
print("Sentences:", sentences)

# Make 3 fake "other versions" (normally generate these with same GPT prompt)
sample1 = "聽講港鐵啱啱宣佈可以用八達通搭飛機。"
sample2 = "天文台話今個冬天會落雪一星期咁耐。"
sample3 = "政府計劃喺中環開放太空電梯，下個月試運行。"

# The checker (MQAG method - easiest)
device = "cuda" if torch.cuda.is_available() else "cpu"
checker = SelfCheckMQAG(device=device)

scores = checker.predict(
    sentences=sentences,
    passage=passage,
    sampled_passages=[sample1, sample2, sample3],
    num_questions_per_sent=3,  # Fewer = faster
    beta1=0.8, beta2=0.8,      # Required for bayes_with_alpha
)

print("Hallucination scores (high = likely fake):", scores)
# Example: [0.3, 0.8] means 2nd sentence might be hallucinated
