import React, { useEffect, useState } from 'react'
import { useContextsStore } from '@/stores/contexts'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select"
import Button from "@/components/ui/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/AlertDialog"
import Input from "@/components/ui/Input"
import Badge from "@/components/ui/Badge"
import Label from "@/components/ui/Label"
import {
  Loader2,
  Settings,
  Edit,
  Trash,
  FileBox,
  Database,

  PenIcon
} from "lucide-react"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover"
import { formatDistanceToNow } from 'date-fns'

export function ContextSelector() {
  const {
    contexts,
    currentContext,
    isLoading,
    isLoadingStats,
    isMultiContextSupported,
    fetchContexts,
    fetchContextStats,
    createNewContext,
    switchToContext,
    deleteContext,
    renameContext
  } = useContextsStore()

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isManageDialogOpen, setIsManageDialogOpen] = useState(false)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false)
  const [isSwitchDialogOpen, setIsSwitchDialogOpen] = useState(false)
  const [contextToDelete, setContextToDelete] = useState<string | null>(null)
  const [contextToRename, setContextToRename] = useState<string | null>(null)
  const [contextToSwitch, setContextToSwitch] = useState<string | null>(null)
  const [newContextName, setNewContextName] = useState('')
  const [newContextDescription, setNewContextDescription] = useState('')
  const [renameValue, setRenameValue] = useState('')

  useEffect(() => {
    console.log('ContextSelector: fetching contexts')
    fetchContexts()
      .then(() => console.log('ContextSelector: contexts fetched successfully'))
      .catch(error => console.error('ContextSelector: failed to fetch contexts', error))
  }, [fetchContexts])

  // If multi-context is not supported, show simplified UI
  if (!isMultiContextSupported) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 px-3 py-1 text-sm text-gray-600 dark:text-gray-400">
          <FileBox className="h-4 w-4" />
          <span>Default Context</span>
        </div>
      </div>
    )
  }

  const handleCreateContext = async () => {
    if (!newContextName) return
    await createNewContext(newContextName, newContextDescription)
    setIsCreateDialogOpen(false)
    setNewContextName('')
    setNewContextDescription('')
  }

  const handleContextChange = (value: string) => {
    // Don't show confirmation if it's the current context
    if (value === currentContext) return

    // Store the context to switch to and open confirmation dialog
    setContextToSwitch(value)
    setIsSwitchDialogOpen(true)
  }

  const confirmContextSwitch = async () => {
    if (!contextToSwitch) return

    const success = await switchToContext(contextToSwitch)
    setContextToSwitch(null)
    setIsSwitchDialogOpen(false)

    if (success) {
      console.log('Context switch successful, graph data will reload automatically')
      // No longer need to reload the page as the graph data will refresh automatically
      // due to our context.ts store changes and GraphLabels.tsx updates
    }
  }

  const handleDeleteContext = async () => {
    if (!contextToDelete) return

    await deleteContext(contextToDelete)
    setContextToDelete(null)
    setIsDeleteDialogOpen(false)
  }

  const handleRenameContext = async () => {
    if (!contextToRename || !renameValue) return

    await renameContext(contextToRename, renameValue)
    setContextToRename(null)
    setRenameValue('')
    setIsRenameDialogOpen(false)
  }

  const openDeleteDialog = (contextName: string) => {
    setContextToDelete(contextName)
    setIsDeleteDialogOpen(true)
  }

  const openRenameDialog = (contextName: string) => {
    setContextToRename(contextName)
    setRenameValue(contextName) // Initialize with current name
    setIsRenameDialogOpen(true)
  }

  const getContextInfo = (name: string) => {
    return contexts[name]
  }

  const isDefaultContext = (name: string) => {
    const info = getContextInfo(name)
    return info && info.is_default
  }

  const isCurrentContextActive = (name: string) => {
    const info = getContextInfo(name)
    return info && info.is_current
  }

  const getContextCreationDate = (name: string) => {
    const info = getContextInfo(name)
    if (info && info.created_at) {
      return formatDistanceToNow(new Date(info.created_at), { addSuffix: true })
    }
    return 'Unknown'
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNewContextName(e.target.value)
  }

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNewContextDescription(e.target.value)
  }

  const handleRenameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setRenameValue(e.target.value)
  }

  return (
    <div className="flex items-center gap-2">
      {/* Context Selector Dropdown */}
      <Select
        value={currentContext || ''}
        onValueChange={handleContextChange}
        disabled={isLoading}
      >
        <SelectTrigger className="w-[200px]">
          <SelectValue placeholder="Select context">
            {currentContext && (
              <div className="flex items-center gap-2">
                <FileBox className="h-4 w-4" />
                <span>{currentContext}</span>
              </div>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {Object.entries(contexts).map(([name, info]) => (
            <SelectItem key={name} value={name} className="relative pl-8">
              <div className="flex items-center gap-2">
                <FileBox className="h-4 w-4 mr-1" />
                <span>{name}</span>
                {info.is_default && (
                  <Badge variant="outline" className="ml-2 px-1 text-xs">Default</Badge>
                )}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {info.description || "No description"}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* New Context Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" disabled={isLoading} size="sm">
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            New
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Context</DialogTitle>
            <DialogDescription>
              Create a new knowledge base context to store and manage your documents.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="name" className="text-right">
                Name
              </label>
              <Input
                id="name"
                value={newContextName}
                onChange={handleInputChange}
                className="col-span-3"
                placeholder="Enter context name"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="description" className="text-right">
                Description
              </Label>
              <Input
                id="description"
                value={newContextDescription}
                onChange={handleDescriptionChange}
                className="col-span-3"
                placeholder="Enter context description (optional)"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateContext} disabled={!newContextName}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Manage Contexts Button & Dialog */}
      <Popover open={isManageDialogOpen} onOpenChange={setIsManageDialogOpen}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Settings className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[300px] p-0">
          <div className="p-3 border-b">
            <h3 className="font-medium">Manage Contexts</h3>
            <p className="text-xs text-gray-500">Organize your knowledge bases</p>
          </div>
          <div className="max-h-[300px] overflow-y-auto">
            {Object.entries(contexts).map(([name, info]) => (
              <div
                key={name}
                className={`p-3 border-b flex items-center justify-between ${
                  isCurrentContextActive(name) ? 'bg-gray-50 dark:bg-gray-800' : ''
                }`}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-1">
                    <FileBox className="h-4 w-4 mr-1" />
                    <span className="font-medium">{name}</span>
                    {info.is_default && (
                      <Badge variant="outline" className="ml-1 px-1 text-xs">Default</Badge>
                    )}
                    {isCurrentContextActive(name) && (
                      <Badge variant="secondary" className="ml-1 px-1 text-xs">Active</Badge>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {info.description || "No description"}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Created: {getContextCreationDate(name)}
                  </div>
                  {info.stats ? (
                    <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      <div>Documents: {info.stats.documents_count}</div>
                      <div>Entities: {info.stats.entities_count}</div>
                      <div>Relationships: {info.stats.relationships_count}</div>
                      <div>Size: {info.stats.disk_usage_mb.toFixed(1)} MB</div>
                    </div>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-1 h-6 text-xs px-2"
                      onClick={() => fetchContextStats(name)}
                      disabled={isLoadingStats}
                    >
                      {isLoadingStats ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                      Load Stats
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => openRenameDialog(name)}
                  >
                    <PenIcon className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-red-500"
                    onClick={() => openDeleteDialog(name)}
                    disabled={Object.keys(contexts).length <= 1}
                  >
                    <Trash className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </PopoverContent>
      </Popover>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the context "{contextToDelete}" and all its associated data.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setContextToDelete(null)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteContext} className="bg-red-600 hover:bg-red-700">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Rename Dialog */}
      <Dialog open={isRenameDialogOpen} onOpenChange={setIsRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Context</DialogTitle>
            <DialogDescription>
              Enter a new name for the context "{contextToRename}".
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              value={renameValue}
              onChange={handleRenameChange}
              placeholder="New context name"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setContextToRename(null)
              setIsRenameDialogOpen(false)
            }}>
              Cancel
            </Button>
            <Button onClick={handleRenameContext} disabled={!renameValue || renameValue === contextToRename}>
              Rename
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Context Switch Confirmation Dialog */}
      <AlertDialog open={isSwitchDialogOpen} onOpenChange={setIsSwitchDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch Context</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to switch to the "{contextToSwitch}" context?
              This will change your current working environment and the documents you are working with.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setContextToSwitch(null)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction onClick={confirmContextSwitch}>
              Switch Context
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
