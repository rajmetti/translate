import './App.css'
import BookTranslator from './BookTranslator'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Book Translator</h1>
        <p>Translate EPUB and PDF books using Microsoft Foundry models</p>
      </header>
      <main>
        <BookTranslator />
      </main>
    </div>
  )
}

export default App
