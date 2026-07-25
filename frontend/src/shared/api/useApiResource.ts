import {useEffect, useState, type DependencyList} from 'react';

interface ApiResourceState<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
}

export function useApiResource<T>(
  loader: () => Promise<T>,
  dependencies: DependencyList,
): ApiResourceState<T> {
  const [state, setState] = useState<ApiResourceState<T>>({
    data: null,
    error: null,
    isLoading: true,
  });

  useEffect(() => {
    let isActive = true;

    setState((current) => ({...current, isLoading: true, error: null}));
    loader()
      .then((data) => {
        if (isActive) {
          setState({data, error: null, isLoading: false});
        }
      })
      .catch((error: unknown) => {
        if (isActive) {
          const message = error instanceof Error ? error.message : 'Failed to load data';
          setState({data: null, error: message, isLoading: false});
        }
      });

    return () => {
      isActive = false;
    };
  }, dependencies);

  return state;
}
