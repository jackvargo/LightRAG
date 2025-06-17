import { create } from 'zustand'
import { 
  ContextInfo, 
  ContextStats,
  getContexts, 
  getContextStats,
  createContext, 
  switchContext, 
  renameContext, 
  deleteContext,
  queryGraphs 
} from '@/api/lightrag'
import { useGraphStore } from './graph'

interface ContextsState {
  contexts: Record<string, ContextInfo>
  currentContext: string | null
  isLoading: boolean
  isLoadingStats: boolean
  error: string | null
  isMultiContextSupported: boolean
  
  // Actions
  fetchContexts: () => Promise<void>
  fetchContextStats: (contextName: string) => Promise<ContextStats | null>
  createNewContext: (name: string, description: string) => Promise<void>
  switchToContext: (name: string) => Promise<boolean>
  renameContext: (oldName: string, newName: string) => Promise<void>
  deleteContext: (name: string) => Promise<void>
  refreshGraph: () => Promise<void>
  clearError: () => void
}

export const useContextsStore = create<ContextsState>((set, get) => ({
  contexts: {},
  currentContext: null,
  isLoading: false,
  isLoadingStats: false,
  error: null,
  isMultiContextSupported: true,

  fetchContexts: async () => {
    set({ isLoading: true, error: null })
    try {
      console.log('contexts store: fetching contexts')
      const response = await getContexts()
      console.log('contexts store: received response', response)
      set({
        contexts: response.contexts,
        currentContext: response.current_context,
        isLoading: false,
        isMultiContextSupported: true
      })
    } catch (error) {
      console.warn('contexts store: multi-context not supported, falling back to single-context mode', error)
      // Fall back to single-context mode
      set({ 
        contexts: { 'default': { description: 'Default context', path: '', created_at: new Date().toISOString() } },
        currentContext: 'default',
        isLoading: false,
        isMultiContextSupported: false,
        error: null
      })
    }
  },
  
  fetchContextStats: async (contextName: string) => {
    set({ isLoadingStats: true })
    try {
      const stats = await getContextStats(contextName)
      
      // Update the contexts state with the new stats
      const updatedContexts = { ...get().contexts }
      if (updatedContexts[contextName]) {
        updatedContexts[contextName] = {
          ...updatedContexts[contextName],
          stats
        }
        set({ contexts: updatedContexts })
      }
      
      set({ isLoadingStats: false })
      return stats
    } catch (error) {
      set({ 
        error: error instanceof Error ? error.message : 'Failed to fetch context statistics',
        isLoadingStats: false
      })
      return null
    }
  },

  createNewContext: async (name: string, description: string) => {
    set({ isLoading: true, error: null })
    try {
      await createContext(name, description)
      await get().fetchContexts()
      await get().refreshGraph()
      set({ isLoading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to create context', isLoading: false })
    }
  },

  switchToContext: async (name: string) => {
    set({ isLoading: true, error: null })
    try {
      const result = await switchContext(name)
      set({ currentContext: name })
      
      // Reset graph store states to ensure clean loading
      useGraphStore.getState().reset()
      
      // Reset fetchAttempted flags to force a fresh data load
      useGraphStore.getState().setGraphDataFetchAttempted(false)
      useGraphStore.getState().setLabelsFetchAttempted(false)
      
      // Refresh the graph after switching context
      await get().refreshGraph()
      
      set({ isLoading: false })
      return true
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to switch context', isLoading: false })
      return false
    }
  },

  renameContext: async (oldName: string, newName: string) => {
    set({ isLoading: true, error: null })
    try {
      await renameContext(oldName, newName)
      await get().fetchContexts()
      set({ isLoading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to rename context', isLoading: false })
    }
  },
  
  deleteContext: async (name: string) => {
    set({ isLoading: true, error: null })
    try {
      await deleteContext(name)
      await get().fetchContexts()
      await get().refreshGraph()
      set({ isLoading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to delete context', isLoading: false })
    }
  },

  refreshGraph: async () => {
    try {
      console.log('Refreshing graph data after context switch')
      
      // Set graph as loading
      useGraphStore.getState().setIsFetching(true)
      
      // Force a fresh data load by clearing last successful query label
      useGraphStore.getState().setLastSuccessfulQueryLabel('')
      
      // Fetch all graph labels first to populate dropdown
      await useGraphStore.getState().fetchAllDatabaseLabels()
      
      // Load the graph data with a default query
      await queryGraphs('*', 3, 1000)
      
      // Finish loading
      useGraphStore.getState().setIsFetching(false)
      
      console.log('Graph data refreshed successfully')
    } catch (error) {
      console.error('Failed to refresh graph:', error)
      useGraphStore.getState().setIsFetching(false)
      set({ error: error instanceof Error ? error.message : 'Failed to refresh graph' })
    }
  },
  
  clearError: () => {
    set({ error: null })
  }
})) 