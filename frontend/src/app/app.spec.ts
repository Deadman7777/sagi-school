import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  // Le test « should render title » du squelette `ng new` a été retiré : il
  // attendait « Hello, frontend » dans un <h1>, contenu disparu le jour où
  // l'application a été écrite. Il échouait depuis, et une suite rouge en
  // permanence est une suite que personne ne lance.
});
