import copy,io,os,unittest
from pathlib import Path
from PIL import Image
from pydantic_ai.messages import BinaryContent,ToolReturnPart
from pydantic_ai_harness.compaction import _shared
from rpent_local_compaction import install,CONFIG
class Compaction(unittest.TestCase):
 def test_image_payload_preserved_and_counted(self):
  original=_shared._request_part_text
  try:
   count,parts=install(Path(os.environ['RSI_RUNTIME_ROOT'])/'models/Qwen3-VL-8B-Instruct/tokenizer.json','/tmp/rsi-cpu-unused-compaction.jsonl')
   b=io.BytesIO();Image.new('RGB',(640,480)).save(b,format='PNG')
   image=BinaryContent(data=b.getvalue(),media_type='image/png')
   part=ToolReturnPart(tool_name='read_image',content=['evidence',image],tool_call_id='test')
   before=copy.deepcopy(part);text=parts(part)
   self.assertEqual(part,before);self.assertEqual(text[0],'evidence');self.assertEqual(count(text[1]),302)
   self.assertGreater(count('test native task language'),0)
   import rpent.planner.api_loop as api
   compactor=api.SlidingWindowCompaction(max_messages=2)
   self.assertEqual(compactor.max_tokens,28672)
  finally:_shared._request_part_text=original
 def test_output_scope(self):
  self.assertEqual(CONFIG['keep_tokens'],24000);self.assertTrue(CONFIG['preserve_first_user_message'])
if __name__=='__main__':unittest.main()
