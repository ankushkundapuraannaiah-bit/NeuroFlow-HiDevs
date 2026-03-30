import axios from 'axios';
import { useQuery, useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

export const usePipelines = () => useSuspenseQuery({
  queryKey: ['pipelines'],
  queryFn: () => api.get('/pipelines').then(res => res.data),
});

export const usePipelineRuns = (pipelineId: string) => useQuery({
  queryKey: ['pipeline', pipelineId, 'runs'],
  queryFn: () => api.get(`/pipelines/${pipelineId}/runs`).then(res => res.data),
});

export const useSubmitQuery = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pipelineId, query }: { pipelineId: string; query: string }) =>
      api.post('/query', { pipeline_id: pipelineId, query }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluations'] });
    },
  });
};

export const useSSEStream = (runId: string) => {
  return useQuery({
    queryKey: ['stream', runId],
    queryFn: async () => {
      const eventSource = new EventSource(`/api/runs/${runId}/stream`);
      return new Promise<{ content: string; done: boolean }>((resolve) => {
        eventSource.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.done) {
            eventSource.close();
            resolve(data);
          }
        };
      });
    },
    refetchInterval: 1000,
    refetchOnWindowFocus: false,
  });
};

export const useSubmitFeedback = () => useMutation({
  mutationFn: ({ runId, rating }: { runId: string; rating: 1 | 5 }) =>
    api.patch(`/runs/${runId}/rating`, { rating }),
});