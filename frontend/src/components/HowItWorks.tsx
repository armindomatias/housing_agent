import { Link, Brain, Calculator } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

const steps = [
  {
    icon: Link,
    step: "Passo 1",
    title: "Cole o URL",
    description: "Copie o link do anúncio do Idealista e cole aqui.",
  },
  {
    icon: Brain,
    step: "Passo 2",
    title: "Análise por IA",
    description: "A IA analisa as fotos do imóvel divisão a divisão.",
  },
  {
    icon: Calculator,
    step: "Passo 3",
    title: "Estimativa",
    description: "Receba custos detalhados de remodelação por divisão.",
  },
];

export function HowItWorks() {
  return (
    <section className="w-full bg-muted py-16 px-4">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-10">Como funciona?</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {steps.map(({ icon: Icon, step, title, description }) => (
            <Card key={step} className="bg-background border-border">
              <CardContent className="pt-6 text-center flex flex-col items-center gap-3">
                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary/10">
                  <Icon className="w-6 h-6 text-primary" />
                </div>
                <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  {step}
                </span>
                <h3 className="font-semibold text-foreground">{title}</h3>
                <p className="text-sm text-muted-foreground">{description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
