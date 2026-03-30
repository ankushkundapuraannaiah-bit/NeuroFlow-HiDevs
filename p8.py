# In run_pipeline method
async def run_pipeline(self, pipeline_id, query):
    runner = WrappedOpenAIClient(self.redis, self.openai)
    
    # Retrieval with circuit breaker + timeout + rate limit
    async with runner.rl.limit("openai", str(pipeline_id), config["retrieval"]["rpm"]):
        async with runner.cb(lambda: self.retrieve_chunks(query)):
            chunks = await self.tm.with_timeout(
                self.retrieve_chunks(query),
                "embedding"
            )
    
    # Generation
    answer = await runner.complete(messages, str(pipeline_id), config["generation"]["rpm"])