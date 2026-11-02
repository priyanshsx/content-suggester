#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
from suggester.core.config import Config
from suggester.core.schemas import Query
#--------------------------------------------------------------#

# Build all queries for one source
def build_queries(cfg: Config, source: str) -> list[Query]:
    template = cfg.query_templates.get(source)
    if template is None:
        return []
    queries, seen = [], set()
    for topic in cfg.topics:
        for lang, keywords in topic.keywords.items():
            for kw in keywords:
                text = template.format(keyword=kw)
                if text in seen:                     # same keyword listed twice
                    continue
                seen.add(text)
                queries.append(Query(text=text, keyword=kw, topic=topic.name,
                                     pillar=topic.pillar, language=lang))
    return queries
#--------------------------------------------------------------#

# Run directly to preview the queries for a client
if __name__ == "__main__":
    import sys

    from suggester.core.config import load_config
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "vizcorn")
    total = 0
    for src in cfg.sources:
        qs = build_queries(cfg, src)
        total += len(qs)
        print(f"\n{src}: {len(qs)} queries")
        for q in qs:
            print(f"  [{q.language}] {q.text}")
    print(f"\nTotal paid searches per run: {total}")
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#