'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

export default function LoginPage() {
  const { signIn, signUp } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(mode: 'signin' | 'signup') {
    setError(null)
    setSubmitting(true)
    try {
      if (mode === 'signin') {
        await signIn(email, password)
      } else {
        await signUp(email, password)
      }
      router.replace('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0E1117] p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-[#00D4AA]">MoleCopilot</h1>
          <p className="mt-1 text-sm text-[#8B949E]">Molecular Docking Research</p>
        </div>

        <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
          <Tabs defaultValue="signin">
            <CardHeader>
              <CardTitle>
                <TabsList className="w-full">
                  <TabsTrigger value="signin" className="flex-1">Sign In</TabsTrigger>
                  <TabsTrigger value="signup" className="flex-1">Sign Up</TabsTrigger>
                </TabsList>
              </CardTitle>
            </CardHeader>

            <CardContent>
              {error && (
                <div className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-[#FAFAFA]">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-[#FAFAFA]">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="border-[#2A2F3E] bg-[#0E1117] text-[#FAFAFA]"
                  />
                </div>

                <TabsContent value="signin">
                  <Button
                    className="w-full bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                    disabled={submitting}
                    onClick={() => handleSubmit('signin')}
                  >
                    {submitting ? 'Signing in...' : 'Sign In'}
                  </Button>
                </TabsContent>

                <TabsContent value="signup">
                  <Button
                    className="w-full bg-[#00D4AA] text-[#0E1117] hover:bg-[#00D4AA]/80"
                    disabled={submitting}
                    onClick={() => handleSubmit('signup')}
                  >
                    {submitting ? 'Creating account...' : 'Sign Up'}
                  </Button>
                </TabsContent>
              </div>
            </CardContent>
          </Tabs>
        </Card>
      </div>
    </div>
  )
}
