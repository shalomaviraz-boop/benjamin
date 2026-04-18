{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tqr\tx720\tqr\tx1440\tqr\tx2160\tqr\tx2880\tqr\tx3600\tqr\tx4320\tqr\tx5040\tqr\tx5760\tqr\tx6480\tqr\tx7200\tqr\tx7920\tqr\tx8640\pardirnatural\qr\partightenfactor0

\f0\fs24 \cf0 from agents.base_agent import BaseAgent\
from agents.agent_contract import build_agent_result\
from experts.gemini_client import generate_web\
\
\
class AIExpertAgent(BaseAgent):\
    def __init__(self):\
        super().__init__(\
            name="ai_expert",\
            system_prompt=(\
                "You are a world-class AI expert with 40 years of experience in artificial intelligence and machine learning. "\
                "You deeply understand language models, AI systems, tools, agents, prompting, model capabilities, tradeoffs, "\
                "integrations, and real-world use cases. "\
                "You explain clearly, sharply, practically, and without generic fluff. "\
                "You also track major AI updates from OpenAI, Anthropic, Google, Meta, xAI, Mistral and others."\
            ),\
        )\
\
    async def run(self, message: str, context: dict | None = None):\
        context = context or \{\}\
        text = (message or "").lower()\
\
        is_news = any(\
            x in text for x in [\
                "\uc0\u1495 \u1491 \u1513 \u1493 \u1514 ", "\u1506 \u1491 \u1499 \u1493 \u1503 ", "\u1506 \u1491 \u1499 \u1493 \u1504 \u1497 \u1501 ", "\u1502 \u1492  \u1495 \u1491 \u1513 ", "latest", "news",\
                "openai", "anthropic", "claude", "gemini", "gpt",\
                "meta", "llama", "xai", "grok", "mistral"\
            ]\
        )\
\
        if is_news:\
            prompt = (\
                "\uc0\u1506 \u1504 \u1492  \u1489 \u1506 \u1489 \u1512 \u1497 \u1514 . \u1502 \u1491 \u1493 \u1489 \u1512  \u1489 \u1489 \u1511 \u1513 \u1514  \u1495 \u1491 \u1513 \u1493 \u1514  AI \u1493 \u1500 \u1499 \u1503  \u1514 \u1489 \u1497 \u1488  \u1512 \u1511  \u1502 \u1497 \u1491 \u1506  \u1506 \u1491 \u1499 \u1504 \u1497  \u1493 \u1512 \u1500 \u1493 \u1493 \u1504 \u1496 \u1497 . "\
                "\uc0\u1514 \u1503  3 \u1506 \u1491  5 \u1506 \u1491 \u1499 \u1493 \u1504 \u1497 \u1501  \u1492 \u1499 \u1497  \u1495 \u1513 \u1493 \u1489 \u1497 \u1501 . "\
                "\uc0\u1500 \u1499 \u1500  \u1505 \u1506 \u1497 \u1507  \u1510 \u1497 \u1497 \u1503  \u1514 \u1488 \u1512 \u1497 \u1498 , \u1502 \u1492  \u1497 \u1510 \u1488 , \u1502 \u1492  \u1494 \u1492  \u1506 \u1493 \u1513 \u1492 , \u1493 \u1500 \u1502 \u1492  \u1494 \u1492  \u1495 \u1513 \u1493 \u1489 . "\
                "\uc0\u1489 \u1500 \u1497  \u1502 \u1497 \u1491 \u1506  \u1497 \u1513 \u1503  \u1493 \u1489 \u1500 \u1497  \u1495 \u1508 \u1497 \u1512 \u1493 \u1514 .\\n\\n"\
                f"\uc0\u1489 \u1511 \u1513 \u1514  \u1492 \u1502 \u1513 \u1514 \u1502 \u1513 : \{message\}"\
            )\
            output = await generate_web(prompt, web_mode="news")\
        else:\
            prompt = (\
                "\uc0\u1506 \u1504 \u1492  \u1489 \u1506 \u1489 \u1512 \u1497 \u1514  \u1499 \u1502 \u1493 \u1502 \u1495 \u1492  AI \u1489 \u1499 \u1497 \u1512 . "\
                "\uc0\u1514 \u1492 \u1497 \u1492  \u1511 \u1510 \u1512 , \u1495 \u1491 , \u1508 \u1512 \u1511 \u1496 \u1497  \u1493 \u1500 \u1488  \u1490 \u1504 \u1512 \u1497 . "\
                "\uc0\u1488 \u1501  \u1510 \u1512 \u1497 \u1498  \u1492 \u1513 \u1493 \u1493 \u1488 \u1492  \u1489 \u1497 \u1503  \u1502 \u1493 \u1491 \u1500 \u1497 \u1501 /\u1499 \u1500 \u1497 \u1501  \u1514 \u1503  \u1492 \u1502 \u1500 \u1510 \u1492  \u1489 \u1512 \u1493 \u1512 \u1492 .\\n\\n"\
                f"\uc0\u1489 \u1511 \u1513 \u1514  \u1492 \u1502 \u1513 \u1514 \u1502 \u1513 : \{message\}"\
            )\
            output = await generate_web(prompt, web_mode="research")\
\
        return build_agent_result(\
            agent=self.name,\
            output=output,\
            notes="ai expert completed",\
            agent_context=context,\
        )}